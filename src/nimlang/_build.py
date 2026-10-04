"""Compile Nim sources into Python extension modules and executables."""

from __future__ import annotations

import subprocess
import sysconfig
from pathlib import Path

from nimlang._project import find_root, path_args
from nimlang._toolchain import EXE, NimlangError, cc_args, nim_exe

# nimpy resolves the Python C API at runtime, so one build works for every
# CPython 3 version: the module only needs the platform's plain extension suffix.
EXTENSION_FLAGS = ["--app:lib", "--threads:on", "--tlsEmulation:off", "-d:release"]
BINARY_FLAGS = ["-d:release"]


def extension_suffix(target: str | None = None) -> str:
    if target is None:
        return sysconfig.get_config_var("EXT_SUFFIX") or ".so"
    return ".pyd" if "-windows" in target else ".so"


def nim_compile_command(args: list[str], *, target: str | None = None, root: Path | None = None) -> list[str]:
    """``nim c`` command line with zig cc and the project's Nim dependencies wired in."""
    return [str(nim_exe()), "c", *cc_args(target), *path_args(root), *args]


def compile_nim(
    source: Path,
    output: Path,
    *,
    kind: str,
    target: str | None = None,
    extra: list[str] = (),
    root: Path | None = None,
) -> Path:
    """Compile ``source`` to ``output``; ``kind`` is ``"extension"`` or ``"binary"``."""
    flags = {"extension": EXTENSION_FLAGS, "binary": BINARY_FLAGS}[kind]
    root = root or find_root(source.parent)
    output.parent.mkdir(parents=True, exist_ok=True)
    cmd = nim_compile_command([*flags, f"--out:{output}", *extra, str(source)], target=target, root=root)
    result = subprocess.run(cmd)
    if result.returncode != 0:
        raise NimlangError(f"nim failed to compile {source} (exit code {result.returncode})")
    return output


def build_extension(
    source: Path, out_dir: Path | None = None, *, target: str | None = None, extra: list[str] = ()
) -> Path:
    source = Path(source).resolve()
    out_dir = Path(out_dir) if out_dir else source.parent
    output = out_dir.resolve() / f"{source.stem}{extension_suffix(target)}"
    return compile_nim(source, output, kind="extension", target=target, extra=extra)


def build_binary(
    source: Path, out_dir: Path | None = None, *, target: str | None = None, extra: list[str] = ()
) -> Path:
    source = Path(source).resolve()
    out_dir = Path(out_dir) if out_dir else source.parent
    suffix = ".exe" if (target and "-windows" in target) or (not target and EXE) else ""
    output = out_dir.resolve() / f"{source.stem}{suffix}"
    return compile_nim(source, output, kind="binary", target=target, extra=extra)
