"""Repackage a Nim binary distribution into a platform wheel of nimlang.

Same approach as ziglang's make_wheels.py: build the pure-Python nimlang wheel,
then add the Nim distribution under ``nimlang/nim/`` and retag the wheel for the
platform the binaries were built for. Each nimlang release bundles one Nim
version; ``nimlang info`` reports it.

    python scripts/make_wheels.py --nim-dist nim-2.2.6-linux_x64.tar.xz \\
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

# Tools worth shipping; the rest (testament, nim_dbg, nim-gdb, ...) stays out to keep wheels small.
KEEP_BIN = {"nim", "nimsuggest", "nimpretty", "nimgrep", "atlas"}
KEEP_BIN_SUFFIXES = {".dll", ".pem"}
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
        # Windows builds need their DLLs and cacert.pem (for HTTPS from Nim programs) next to the executables.
        if rel.parts[0] == "bin" and path.suffix not in KEEP_BIN_SUFFIXES and path.stem not in KEEP_BIN:
            continue
        yield f"nimlang/nim/{rel.as_posix()}", path


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


def pure_wheel(out: Path) -> Path:
    subprocess.run(["uv", "build", "--wheel", "--out-dir", str(out), str(ROOT)], check=True)
    (wheel,) = out.glob("nimlang-*-py3-none-any.whl")
    return wheel


def make_wheel(home: Path, platform_tag: str, out_dir: Path, tmp: Path) -> Path:
    base = pure_wheel(tmp / "pure")
    name, version = base.name.split("-")[:2]
    dist_info = f"{name}-{version}.dist-info"
    target = out_dir / f"{name}-{version}-py3-none-{platform_tag}.whl"
    out_dir.mkdir(parents=True, exist_ok=True)

    records: list[tuple[str, str, int]] = []
    with zipfile.ZipFile(base) as src, zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as dst:

        def write(arcname: str, data: bytes, mode: int = 0o644) -> None:
            info = zipfile.ZipInfo(arcname, date_time=(2020, 1, 1, 0, 0, 0))
            info.external_attr = (stat.S_IFREG | mode) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            dst.writestr(info, data)
            records.append((arcname, record_hash(data), len(data)))

        for item in src.infolist():
            if item.filename == f"{dist_info}/RECORD":
                continue
            data = src.read(item)
            if item.filename == f"{dist_info}/WHEEL":
                text = data.decode()
                text = text.replace("Root-Is-Purelib: true", "Root-Is-Purelib: false")
                text = text.replace("Tag: py3-none-any", f"Tag: py3-none-{platform_tag}")
                data = text.encode()
            write(item.filename, data, (item.external_attr >> 16) & 0o777 or 0o644)

        for arcname, path in nim_files(home):
            executable = arcname.startswith("nimlang/nim/bin/")
            write(arcname, path.read_bytes(), 0o755 if executable else 0o644)

        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\n")
        writer.writerows(records)
        writer.writerow([f"{dist_info}/RECORD", "", ""])
        write(f"{dist_info}/RECORD", buf.getvalue().encode())
    return target


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--nim-dist", type=Path, required=True)
    p.add_argument(
        "--platform-tag", required=True, help="e.g. manylinux_2_17_x86_64, macosx_11_0_arm64, win_amd64"
    )
    p.add_argument("--out-dir", type=Path, default=ROOT / "dist")
    ns = p.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        home = unpack(ns.nim_dist.resolve(), Path(tmp) / "nim")
        check_glibc(home, ns.platform_tag)
        nim = nim_version(home)
        wheel = make_wheel(home, ns.platform_tag, ns.out_dir.resolve(), Path(tmp))
    print(f"built {wheel} with Nim {nim} ({wheel.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
