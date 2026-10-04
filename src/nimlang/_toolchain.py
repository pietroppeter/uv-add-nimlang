"""Locate the Nim and Zig toolchains and wire them together."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent
BUNDLED_NIM = PKG_DIR / "nim"
EXE = ".exe" if os.name == "nt" else ""

# zig target arch/os -> Nim --cpu/--os
ZIG_TO_NIM_CPU = {
    "x86_64": "amd64",
    "aarch64": "arm64",
    "x86": "i386",
    "arm": "arm",
    "riscv64": "riscv64",
    "powerpc64le": "powerpc64el",
}
ZIG_TO_NIM_OS = {
    "linux": "linux",
    "windows": "windows",
    "macos": "macosx",
    "freebsd": "freebsd",
}


class NimlangError(RuntimeError):
    pass


def _scripts_dir() -> Path:
    return Path(sysconfig.get_path("scripts")).resolve()


def _is_nim_home(path: Path) -> bool:
    return (path / "bin" / f"nim{EXE}").is_file() and (path / "lib" / "system.nim").is_file()


def nim_home() -> Path:
    """Root of the Nim distribution (the directory holding ``bin/`` and ``lib/``).

    Lookup order: ``$NIMLANG_NIM_HOME``, the distribution bundled in the wheel,
    then a ``nim`` found on ``PATH`` (skipping nimlang's own ``nim`` shim).
    """
    env = os.environ.get("NIMLANG_NIM_HOME")
    if env:
        home = Path(env).expanduser().resolve()
        if not _is_nim_home(home):
            raise NimlangError(f"NIMLANG_NIM_HOME={env} does not contain bin/nim and lib/system.nim")
        return home
    if _is_nim_home(BUNDLED_NIM):
        return BUNDLED_NIM
    scripts = _scripts_dir()
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if not entry or Path(entry).resolve() == scripts:
            continue
        candidate = Path(entry) / f"nim{EXE}"
        if candidate.is_file():
            home = candidate.resolve().parent.parent
            if _is_nim_home(home):
                return home
            home = _ask_prefix(candidate)  # e.g. choosenim's proxy executables
            if home and _is_nim_home(home):
                return home
    raise NimlangError(
        "No Nim compiler found. This nimlang install has no bundled Nim "
        "(source or pure-Python build); set NIMLANG_NIM_HOME or put nim on PATH."
    )


def _ask_prefix(nim: Path) -> Path | None:
    try:
        out = subprocess.run(
            [str(nim), "dump", "--dump.format:json", "-"],
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=60,
        ).stdout
        return Path(json.loads(out)["prefixdir"]).resolve()
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        return None


def nim_exe() -> Path:
    return nim_home() / "bin" / f"nim{EXE}"


def nimble_exe() -> Path:
    path = nim_home() / "bin" / f"nimble{EXE}"
    if not path.is_file():
        raise NimlangError(f"nimble not found next to nim in {path.parent}")
    return path


def zig_exe() -> Path:
    try:
        import ziglang
    except ImportError as e:  # pragma: no cover - ziglang is a hard dependency
        raise NimlangError("the ziglang package is not installed") from e
    path = Path(ziglang.__file__).resolve().parent / f"zig{EXE}"
    if not path.is_file():
        raise NimlangError(f"zig binary missing from ziglang package at {path}")
    return path


def _cache_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "nimlang"


def zigcc_shim() -> Path:
    """A tiny executable script that forwards to ``zig cc``.

    Nim invokes the C compiler as a single executable, so we cannot point it at
    ``zig`` directly. The shim embeds the absolute path of this environment's zig
    and is cached per zig location.
    """
    zig = zig_exe()
    key = hashlib.sha256(str(zig).encode()).hexdigest()[:12]
    folder = _cache_dir() / f"zigcc-{key}"
    if os.name == "nt":
        shim = folder / "zigcc.cmd"
        content = f'@"{zig}" cc %*\r\n'
    else:
        shim = folder / "zigcc"
        content = f'#!/bin/sh\nexec "{zig}" cc "$@"\n'
    if shim.is_file() and shim.read_text() == content:
        return shim
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / f".{shim.name}.{os.getpid()}"
    tmp.write_text(content)
    tmp.chmod(0o755)
    os.replace(tmp, shim)
    return shim


def target_args(target: str) -> list[str]:
    """Nim flags to cross-compile for a zig target triple such as ``aarch64-macos``
    or ``x86_64-linux-gnu.2.17`` (the glibc suffix gives manylinux-compatible output)."""
    parts = target.split("-")
    if len(parts) < 2:
        raise NimlangError(f"invalid zig target {target!r}, expected <arch>-<os>[-<abi>]")
    arch, os_name = parts[0], parts[1]
    if arch not in ZIG_TO_NIM_CPU or os_name not in ZIG_TO_NIM_OS:
        raise NimlangError(f"unsupported zig target {target!r}")
    return [
        f"--cpu:{ZIG_TO_NIM_CPU[arch]}",
        f"--os:{ZIG_TO_NIM_OS[os_name]}",
        f"--passC:-target {target}",
        f"--passL:-target {target}",
    ]


def cc_args(target: str | None = None) -> list[str]:
    """Nim command-line flags that make it compile C through ``zig cc``.

    Set ``NIMLANG_CC=system`` to keep Nim's default C compiler instead.
    """
    if os.environ.get("NIMLANG_CC", "zig") == "system":
        if target:
            raise NimlangError("cross-compiling with a target requires zig cc (unset NIMLANG_CC)")
        return []
    shim = zigcc_shim()
    args = ["--cc:clang", f"--clang.exe:{shim}", f"--clang.linkerexe:{shim}"]
    if target:
        args += target_args(target)
    return args


def nim_shim_path() -> str:
    """Path of nimlang's ``nim`` console script if installed, else the raw compiler.

    Handed to nimble so that packages it builds also compile through zig cc.
    """
    shim = _scripts_dir() / f"nim{EXE}"
    if shim.is_file():
        return str(shim)
    found = shutil.which("nim")
    return found or str(nim_exe())
