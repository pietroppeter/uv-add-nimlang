"""Project-level state: Nim dependencies declared in pyproject.toml.

Dependencies live in ``[tool.nimlang] dependencies`` as nimble requirement
strings (``"nimpy"``, ``"nimpy >= 0.2.0"``, ``"nimpy@#head"``) and are installed
by nimble into ``.nimlang/nimble`` next to pyproject.toml.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

import tomlkit

from nimlang._toolchain import nim_shim_path, nimble_exe

STATE_DIR = ".nimlang"


def find_root(start: Path | None = None) -> Path | None:
    """Closest directory at or above ``start`` holding a pyproject.toml."""
    here = (start or Path.cwd()).resolve()
    for folder in (here, *here.parents):
        if (folder / "pyproject.toml").is_file():
            return folder
    return None


def nimble_dir(root: Path) -> Path:
    return root / STATE_DIR / "nimble"


def dep_name(requirement: str) -> str:
    """``"nimpy >= 0.2"`` -> ``"nimpy"``; also handles ``pkg@#rev`` and URLs."""
    req = requirement.strip()
    if "://" in req:
        req = req.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
    return re.split(r"[\s@<>=~^#]", req, maxsplit=1)[0].lower()


def _load(root: Path) -> tomlkit.TOMLDocument:
    return tomlkit.parse((root / "pyproject.toml").read_text(encoding="utf-8"))


def read_deps(root: Path) -> list[str]:
    tool = _load(root).get("tool", {})
    return [str(d) for d in tool.get("nimlang", {}).get("dependencies", [])]


def write_deps(root: Path, deps: list[str]) -> None:
    doc = _load(root)
    tool = doc.setdefault("tool", tomlkit.table(is_super_table=True))
    section = tool.setdefault("nimlang", tomlkit.table())
    array = tomlkit.array()
    array.extend(deps)
    if len(deps) > 1:
        array.multiline(True)
    section["dependencies"] = array
    (root / "pyproject.toml").write_text(tomlkit.dumps(doc), encoding="utf-8")


def add_deps(root: Path, requirements: list[str]) -> list[str]:
    """Add or replace requirements (matched by package name); returns the new list."""
    deps = read_deps(root)
    for req in requirements:
        name = dep_name(req)
        deps = [d for d in deps if dep_name(d) != name] + [req.strip()]
    write_deps(root, deps)
    return deps


def remove_deps(root: Path, names: list[str]) -> list[str]:
    drop = {dep_name(n) for n in names}
    deps = [d for d in read_deps(root) if dep_name(d) not in drop]
    write_deps(root, deps)
    return deps


def _version_key(version: str) -> tuple:
    return tuple(int(p) if p.isdigit() else -1 for p in re.split(r"[.\-]", version))


def installed_packages(root: Path) -> dict[str, Path]:
    """Installed package name -> directory, keeping the highest version of each.

    Nimble 0.14+ installs into ``pkgs2/<name>-<version>-<checksum>``; older
    layouts use ``pkgs/<name>-<version>``.
    """
    best: dict[str, tuple[tuple, Path]] = {}
    for sub in ("pkgs", "pkgs2"):
        base = nimble_dir(root) / sub
        if not base.is_dir():
            continue
        for pkg in base.iterdir():
            if not pkg.is_dir():
                continue
            parts = pkg.name.split("-")
            if sub == "pkgs2" and len(parts) >= 3:
                name, version = "-".join(parts[:-2]), parts[-2]
            elif len(parts) >= 2:
                name, version = "-".join(parts[:-1]), parts[-1]
            else:
                continue
            key = _version_key(version)
            if name.lower() not in best or key > best[name.lower()][0]:
                best[name.lower()] = (key, pkg)
    return {name: path for name, (_, path) in best.items()}


def path_args(root: Path | None) -> list[str]:
    """Nim flags exposing exactly this project's installed Nim dependencies.

    ``--noNimblePath`` hides packages from the global ~/.nimble so builds only
    see what pyproject.toml declares.
    """
    if root is None or not nimble_dir(root).is_dir():
        return []
    return ["--noNimblePath"] + [f"--path:{p}" for p in installed_packages(root).values()]


def run_nimble(args: list[str], cwd: Path | str | None = None) -> int:
    """Run the bundled nimble, compiling through nimlang's nim (and so zig cc)."""
    return subprocess.run([str(nimble_exe()), f"--nim:{nim_shim_path()}", *args], cwd=cwd).returncode


def sync(root: Path) -> int:
    """Install the declared Nim dependencies into the project's private nimble dir."""
    deps = read_deps(root)
    if not deps:
        print("nimlang: no Nim dependencies declared in [tool.nimlang]")
        return 0
    folder = nimble_dir(root).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    gitignore = folder.parent / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("*\n")
    # Run outside the project: nimble calls git from its working directory, and git fails
    # there if a parent holds a .git file that is not a repository. uv's cache has one, so
    # building a wheel from an sdist (unpacked inside that cache) broke.
    with tempfile.TemporaryDirectory(prefix="nimlang-sync-") as cwd:
        return run_nimble([f"--nimbleDir:{folder}", "install", "-y", *deps], cwd=cwd)


def missing_deps(root: Path) -> list[str]:
    installed = installed_packages(root)
    return [d for d in read_deps(root) if dep_name(d) not in installed]
