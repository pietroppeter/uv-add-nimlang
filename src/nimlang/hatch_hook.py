"""Hatchling build hook: ship Nim-built extensions and executables in wheels.

Usage in a project that depends on nimlang at build time::

    [build-system]
    requires = ["hatchling", "nimlang"]
    build-backend = "hatchling.build"

    [tool.hatch.build.hooks.nimlang]
    extensions = ["src/mypkg/_core.nim"]   # nimpy modules, importable as mypkg._core
    binaries = ["src/mypkg/mytool.nim"]    # installed as `mytool` on PATH
    # target = "aarch64-macos"             # optional zig target; also $NIMLANG_TARGET
    # strip = false                        # keep debug symbols (stripped by default)

Because nimpy modules do not link against a specific Python, wheels are tagged
``py3-none-<platform>``: one wheel per platform, not per Python version. Every
platform can be built from a single machine by setting the zig target.
"""

from __future__ import annotations

import os
import platform
import sys
import sysconfig
import tempfile
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface
from hatchling.plugin import hookimpl

from nimlang import _project
from nimlang._build import build_binary, build_extension
from nimlang._toolchain import NimlangError

MANYLINUX_GLIBC = "2.17"
# Minimum macOS for wheels, matching nimlang's own wheels. Without it zig targets
# a recent macOS (13.0 with zig 0.16), which the wheel tag would not reflect.
MACOS_MIN = {"aarch64": "11.0", "x86_64": "10.13"}

_LINUX_ARCH = {"x86_64": "x86_64", "amd64": "x86_64", "aarch64": "aarch64", "arm64": "aarch64"}
_MAC_ARCH = {"aarch64": "arm64", "x86_64": "x86_64"}
_WIN_TAG = {"x86_64": "win_amd64", "aarch64": "win_arm64", "x86": "win32"}


def default_target() -> str | None:
    """Pin glibc on Linux (manylinux) and the minimum version on macOS; elsewhere build natively."""
    arch = _LINUX_ARCH.get(platform.machine().lower())
    if arch and sys.platform.startswith("linux"):
        return f"{arch}-linux-gnu.{MANYLINUX_GLIBC}"
    if arch and sys.platform == "darwin":
        return f"{arch}-macos"
    return None


def pin_target(target: str | None) -> str | None:
    """Add the default minimum macOS version to a macOS target that has none."""
    if target is None:
        return None
    arch, os_name, *rest = target.split("-")
    if os_name == "macos" and arch in MACOS_MIN:
        return "-".join([arch, f"macos.{MACOS_MIN[arch]}", *rest])
    return target


def platform_tag(target: str | None) -> str:
    if target is None:
        return sysconfig.get_platform().replace("-", "_").replace(".", "_")
    arch, os_name, *rest = target.split("-")
    abi = rest[0] if rest else ""
    if os_name == "linux":
        if abi.startswith("musl"):
            return f"musllinux_1_2_{arch}"
        glibc = abi.partition(".")[2] or MANYLINUX_GLIBC
        return f"manylinux_{glibc.replace('.', '_')}_{arch}"
    os_name, _, os_version = os_name.partition(".")
    if os_name == "macos" and arch in _MAC_ARCH:
        major, minor = (os_version or MACOS_MIN[arch]).split(".")[:2]
        return f"macosx_{major}_{minor}_{_MAC_ARCH[arch]}"
    if os_name == "windows" and arch in _WIN_TAG:
        return _WIN_TAG[arch]
    raise NimlangError(f"no wheel platform tag known for zig target {target!r}")


def _wheel_path(root: Path, source: Path) -> Path:
    """Where a file built from ``source`` lives inside the wheel (src-layout aware)."""
    rel = source.relative_to(root)
    return rel.relative_to("src") if rel.parts[0] == "src" else rel


class NimlangBuildHook(BuildHookInterface):
    PLUGIN_NAME = "nimlang"

    def initialize(self, version: str, build_data: dict) -> None:
        if self.target_name != "wheel":
            return
        root = Path(self.root)
        extensions = [root / p for p in self.config.get("extensions", [])]
        binaries = [root / p for p in self.config.get("binaries", [])]
        if not extensions and not binaries:
            return
        if _project.read_deps(root) and _project.sync(root) != 0:
            raise NimlangError("installing the Nim dependencies from [tool.nimlang] failed")
        target = pin_target(os.environ.get("NIMLANG_TARGET") or self.config.get("target") or default_target())
        # Strip symbols from release artifacts: it shrinks a nimpy module about 7x.
        extra = ["--passL:-s"] if self.config.get("strip", True) else []

        if version == "editable":
            # Editable installs import from the source tree: build modules in place.
            for src in extensions:
                build_extension(src, target=target)
            if binaries:
                self.app.display_warning("nimlang: binaries are not built for editable installs")
            return

        self._tmp = tempfile.TemporaryDirectory(prefix="nimlang-build-")
        out = Path(self._tmp.name)
        for src in extensions:
            built = build_extension(src, out / "ext", target=target, extra=extra)
            dest = _wheel_path(root, src).with_name(built.name)
            build_data["force_include"][str(built)] = str(dest)
        for src in binaries:
            built = build_binary(src, out / "bin", target=target, extra=extra)
            build_data["shared_scripts"][str(built)] = built.name

        build_data["pure_python"] = False
        build_data["tag"] = f"py3-none-{platform_tag(target)}"

    def finalize(self, version: str, build_data: dict, artifact_path: str) -> None:
        tmp = getattr(self, "_tmp", None)
        if tmp is not None:
            tmp.cleanup()


@hookimpl
def hatch_register_build_hook():
    return NimlangBuildHook
