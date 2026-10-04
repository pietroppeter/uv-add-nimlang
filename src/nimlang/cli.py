"""Command-line entry points: ``nimlang``, plus ``nim`` and ``nimble`` shims."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from nimlang import _project
from nimlang._build import build_binary, build_extension
from nimlang._toolchain import (
    NimlangError,
    cc_args,
    nim_exe,
    nim_home,
    nim_version,
    zig_exe,
    zigcc_shim,
)

# Commands that invoke the C compiler get zig cc; commands that only resolve
# imports get the project's dependency paths. Everything else (notably `nim e`,
# which nimble uses to evaluate .nimble files) passes through untouched, since
# NimScript sees every command-line argument.
_C_COMMANDS = {"c", "cc", "cpp", "objc", "compile", "compiletoc", "compiletocpp", "compiletooc", "r", "run"}
_PATH_COMMANDS = {"js", "check", "doc", "doc2", "jsondoc", "ctags", "dump"}


def _run(cmd: list[str]) -> int:
    try:
        return subprocess.run(cmd).returncode
    except KeyboardInterrupt:
        return 130


def nim_args(args: list[str]) -> list[str]:
    """Insert nimlang's flags right after the command, so user flags still override them."""
    index = next((i for i, a in enumerate(args) if not a.startswith("-")), None)
    if index is None:
        return args
    command = args[index].lower()
    if command in _C_COMMANDS:
        extra = cc_args() + _project.path_args(_project.find_root())
    elif command in _PATH_COMMANDS:
        extra = _project.path_args(_project.find_root())
    else:
        return args
    return [*args[: index + 1], *extra, *args[index + 1 :]]


def run_nim(args: list[str]) -> int:
    return _run([str(nim_exe()), *nim_args(args)])


def run_nimble(args: list[str]) -> int:
    try:
        return _project.run_nimble(args)
    except KeyboardInterrupt:
        return 130


def _require_root() -> Path:
    root = _project.find_root()
    if root is None:
        raise NimlangError("no pyproject.toml found in this directory or its parents")
    return root


def cmd_add(ns: argparse.Namespace) -> int:
    root = _require_root()
    deps = _project.add_deps(root, ns.packages)
    print(f"nimlang: Nim dependencies: {', '.join(deps)}")
    return 0 if ns.no_sync else _project.sync(root)


def cmd_remove(ns: argparse.Namespace) -> int:
    root = _require_root()
    deps = _project.remove_deps(root, ns.packages)
    print(f"nimlang: Nim dependencies: {', '.join(deps) or '(none)'}")
    return 0


def cmd_sync(ns: argparse.Namespace) -> int:
    return _project.sync(_require_root())


def cmd_build_ext(ns: argparse.Namespace) -> int:
    for source in ns.sources:
        out = build_extension(Path(source), ns.out_dir, target=ns.target, extra=ns.nim_args)
        print(f"nimlang: built {out}")
    return 0


def cmd_build_bin(ns: argparse.Namespace) -> int:
    for source in ns.sources:
        out = build_binary(Path(source), ns.out_dir, target=ns.target, extra=ns.nim_args)
        print(f"nimlang: built {out}")
    return 0


def cmd_info(ns: argparse.Namespace) -> int:
    root = _project.find_root()
    rows = [
        ("nim", f"{nim_version()} at {nim_home()}"),
        ("zig", zig_exe()),
        ("zigcc shim", zigcc_shim()),
        ("project", root or "(none)"),
    ]
    if root:
        rows.append(("nim deps", ", ".join(_project.read_deps(root)) or "(none)"))
        rows.append(("installed", ", ".join(sorted(_project.installed_packages(root))) or "(none)"))
    for key, value in rows:
        print(f"{key:>11}: {value}")
    return 0


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="nimlang", description="Nim toolchain for Python projects.")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("add", help="add Nim dependencies to pyproject.toml and install them")
    s.add_argument("packages", nargs="+", help='nimble requirements, e.g. nimpy or "nimpy >= 0.2"')
    s.add_argument("--no-sync", action="store_true", help="only edit pyproject.toml")
    s.set_defaults(func=cmd_add)

    s = sub.add_parser("remove", help="remove Nim dependencies from pyproject.toml")
    s.add_argument("packages", nargs="+")
    s.set_defaults(func=cmd_remove)

    s = sub.add_parser("sync", help="install the Nim dependencies declared in pyproject.toml")
    s.set_defaults(func=cmd_sync)

    for name, func, help_ in (
        ("build-ext", cmd_build_ext, "compile .nim files into Python extension modules (nimpy)"),
        ("build-bin", cmd_build_bin, "compile .nim files into executables"),
    ):
        s = sub.add_parser(name, help=help_)
        s.add_argument("sources", nargs="+")
        s.add_argument("-o", "--out-dir", type=Path, help="output directory (default: next to source)")
        s.add_argument("--target", help="zig target to cross-compile for, e.g. aarch64-macos")
        s.add_argument("--nim-arg", dest="nim_args", action="append", default=[], help="extra flag for nim")
        s.set_defaults(func=func)

    s = sub.add_parser("info", help="show where the toolchain lives")
    s.set_defaults(func=cmd_info)

    # Passthroughs are handled before argparse so their flags are not parsed.
    sub.add_parser("nim", help="run the Nim compiler (same as the `nim` command)")
    sub.add_parser("nimble", help="run nimble (same as the `nimble` command)")
    return p


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        if argv and argv[0] == "nim":
            return run_nim(argv[1:])
        if argv and argv[0] == "nimble":
            return run_nimble(argv[1:])
        ns = _parser().parse_args(argv)
        return ns.func(ns)
    except NimlangError as e:
        print(f"nimlang: error: {e}", file=sys.stderr)
        return 1


def nim_main() -> int:
    return main(["nim", *sys.argv[1:]])


def nimble_main() -> int:
    return main(["nimble", *sys.argv[1:]])
