"""Package a Nim binary distribution as a ``nimlang-nim`` platform wheel.

Same approach as ziglang's make_wheels.py: the wheel holds the compiler
distribution under ``nimlang_nim/nim/`` and its version is the Nim version, so
projects pick their Nim with ``uv add "nimlang-nim==X.Y.Z"``.

    python scripts/make_nim_wheel.py --nim-dist nim-2.2.6-linux_x64.tar.xz \\
        --platform-tag manylinux_2_17_x86_64

``--nim-dist`` accepts an unpacked directory, a .tar.xz/.tar.gz, or a .zip
containing ``bin/nim`` and ``lib/system.nim`` (optionally under one top folder).
For manylinux tags the ELF files are checked against the tag's glibc version.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "packages" / "nimlang-nim"

# Tools worth shipping; the rest (testament, nim_dbg, nim-gdb, ...) stays out to keep wheels small.
KEEP_BIN = {"nim", "nimble", "nimsuggest", "nimpretty", "nimgrep", "atlas"}
KEEP_TOP = {"bin", "lib", "config", "copying.txt", "LICENSE", "license.txt"}


def find_home(folder: Path) -> Path:
    for candidate in [folder, *folder.rglob("*")]:
        if (
            candidate.is_dir()
            and (candidate / "lib" / "system.nim").is_file()
            and (candidate / "bin").is_dir()
        ):
            return candidate
    raise SystemExit(f"no Nim distribution (bin/ + lib/system.nim) found in {folder}")


def unpack(dist: Path, into: Path) -> Path:
    if dist.is_dir():
        return find_home(dist)
    if dist.suffix == ".zip":
        with zipfile.ZipFile(dist) as z:
            z.extractall(into)
    else:
        with tarfile.open(dist) as t:
            t.extractall(into)
    return find_home(into)


def nim_version(home: Path) -> str:
    text = (home / "lib" / "system" / "compilation.nim").read_text(encoding="utf-8")
    parts = [re.search(rf"{n}\*.*?=\s*(\d+)", text) for n in ("NimMajor", "NimMinor", "NimPatch")]
    if not all(parts):
        raise SystemExit("cannot read the Nim version from lib/system/compilation.nim")
    return ".".join(p.group(1) for p in parts)


def nim_files(home: Path):
    """Yield (path in wheel, file path) for the parts of the distribution we ship."""
    for path in sorted(home.rglob("*")):
        rel = path.relative_to(home)
        if rel.parts[0] not in KEEP_TOP or not path.is_file():
            continue
        # Windows builds need the DLLs next to the executables.
        if rel.parts[0] == "bin" and path.suffix != ".dll" and Path(rel.parts[-1]).stem not in KEEP_BIN:
            continue
        yield f"nimlang_nim/nim/{rel.as_posix()}", path


def check_glibc(home: Path, platform_tag: str) -> None:
    """Fail if a binary needs a newer glibc than the manylinux tag promises."""
    match = re.match(r"manylinux_(\d+)_(\d+)_", platform_tag)
    if not match:
        return
    allowed = (int(match.group(1)), int(match.group(2)))
    if shutil.which("objdump") is None:
        raise SystemExit("objdump is needed to verify the manylinux tag")
    worst = (0, 0)
    for path in (home / "bin").iterdir():
        if path.read_bytes()[:4] != b"\x7fELF":
            continue
        out = subprocess.run(["objdump", "-T", str(path)], capture_output=True, text=True).stdout
        for major, minor in re.findall(r"GLIBC_(\d+)\.(\d+)", out):
            worst = max(worst, (int(major), int(minor)))
    if worst > allowed:
        raise SystemExit(f"binaries need glibc {worst[0]}.{worst[1]}, newer than {platform_tag} allows")
    print(f"glibc check: binaries need at most {worst[0]}.{worst[1]}, ok for {platform_tag}")


def record_hash(data: bytes) -> str:
    return "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()


def metadata(version: str, nim: str) -> str:
    readme = (PACKAGE / "README.md").read_text(encoding="utf-8")
    return (
        "Metadata-Version: 2.1\n"
        "Name: nimlang-nim\n"
        f"Version: {version}\n"
        f"Summary: The Nim {nim} compiler, packaged as a wheel for nimlang\n"
        "License: MIT\n"
        "Requires-Python: >=3.9\n"
        "Project-URL: Repository, https://github.com/pietroppeter/uv-add-nimlang\n"
        "Description-Content-Type: text/markdown\n"
        f"\n{readme}"
    )


def make_wheel(home: Path, platform_tag: str, out_dir: Path, version: str | None = None) -> Path:
    nim = nim_version(home)
    version = version or nim
    dist_info = f"nimlang_nim-{version}.dist-info"
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"nimlang_nim-{version}-py3-none-{platform_tag}.whl"

    records: list[tuple[str, str, int]] = []
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as dst:

        def write(arcname: str, data: bytes, mode: int = 0o644) -> None:
            info = zipfile.ZipInfo(arcname, date_time=(2020, 1, 1, 0, 0, 0))
            info.external_attr = (stat.S_IFREG | mode) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            dst.writestr(info, data)
            records.append((arcname, record_hash(data), len(data)))

        init = (PACKAGE / "nimlang_nim" / "__init__.py").read_text(encoding="utf-8")
        write("nimlang_nim/__init__.py", init.replace("@NIM_VERSION@", nim).encode())
        for arcname, path in nim_files(home):
            executable = arcname.startswith("nimlang_nim/nim/bin/")
            write(arcname, path.read_bytes(), 0o755 if executable else 0o644)
        write(f"{dist_info}/METADATA", metadata(version, nim).encode())
        wheel = (
            "Wheel-Version: 1.0\nGenerator: nimlang make_nim_wheel.py\n"
            f"Root-Is-Purelib: false\nTag: py3-none-{platform_tag}\n"
        )
        write(f"{dist_info}/WHEEL", wheel.encode())

        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\n")
        writer.writerows(records)
        writer.writerow([f"{dist_info}/RECORD", "", ""])
        dst.writestr(f"{dist_info}/RECORD", buf.getvalue())
    return target


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--nim-dist", type=Path, required=True)
    p.add_argument(
        "--platform-tag", required=True, help="e.g. manylinux_2_17_x86_64, macosx_11_0_arm64, win_amd64"
    )
    p.add_argument("--version", help="wheel version (default: the Nim version; use X.Y.Z.postN for repacks)")
    p.add_argument("--out-dir", type=Path, default=ROOT / "dist")
    ns = p.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        home = unpack(ns.nim_dist.resolve(), Path(tmp) / "nim")
        check_glibc(home, ns.platform_tag)
        wheel = make_wheel(home, ns.platform_tag, ns.out_dir.resolve(), ns.version)
    print(f"built {wheel} ({wheel.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
