"""Hatchling build hook: ship Nim-built extensions and executables in wheels.

Usage in a project that depends on nimlang at build time::

    [build-system]
    requires = ["hatchling", "nimlang"]
    build-backend = "hatchling.build"

    [tool.hatch.build.hooks.nimlang]
    extensions = ["src/mypkg/_core.nim"]   # nimpy modules, importable as mypkg._core
    binaries = ["src/mypkg/mytool.nim"]    # installed as `mytool` on PATH
    # target = "aarch64-macos"             # optional zig target; also $NIMLANG_TARGET

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

_LINUX_ARCH = {"x86_64": "x86_64", "amd64": "x86_64", "aarch64": "aarch64", "arm64": "aarch64"}
_MAC_TAG = {"aarch64": "macosx_11_0_arm64", "x86_64": "macosx_10_12_x86_64"}
_WIN_TAG = {"x86_64": "win_amd64", "aarch64": "win_arm64", "x86": "win32"}


def default_target() -> str | None:
    """On Linux, pin glibc so native wheels are manylinux-compliant; elsewhere build natively."""
    if sys.platform.startswith("linux"):
        arch = _LINUX_ARCH.get(platform.machine().lower())
        if arch:
            return f"{arch}-linux-gnu.{MANYLINUX_GLIBC}"
    return None


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
    if os_name == "macos" and arch in _MAC_TAG:
        return _MAC_TAG[arch]
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
        target = os.environ.get("NIMLANG_TARGET") or self.config.get("target") or default_target()

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
            built = build_extension(src, out / "ext", target=target)
            dest = _wheel_path(root, src).with_name(built.name)
            build_data["force_include"][str(built)] = str(dest)
        for src in binaries:
            built = build_binary(src, out / "bin", target=target)
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
