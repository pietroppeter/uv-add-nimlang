"""Repackage a Nim binary distribution into a platform wheel of nimlang.

Same approach as ziglang's make_wheels.py: build the pure-Python nimlang wheel,
then add the Nim distribution under ``nimlang/nim/`` and retag the wheel for the
platform the binaries were built for.

    python scripts/make_wheels.py --nim-dist nim-2.2.6-linux_x64.tar.xz \
        --platform-tag manylinux_2_17_x86_64

``--nim-dist`` accepts an unpacked directory, a .tar.xz/.tar.gz, or a .zip
containing ``bin/nim`` and ``lib/system.nim`` (optionally under one top folder).
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import os
import stat
import subprocess
import tarfile
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

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


def nim_files(home: Path):
    """Yield (path in wheel, file path) for the parts of the distribution we ship."""
    for path in sorted(home.rglob("*")):
        rel = path.relative_to(home)
        if rel.parts[0] not in KEEP_TOP or not path.is_file():
            continue
        if rel.parts[0] == "bin" and Path(rel.parts[-1]).stem not in KEEP_BIN:
            continue
        yield f"nimlang/nim/{rel.as_posix()}", path


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
            executable = os.access(path, os.X_OK) or arcname.startswith("nimlang/nim/bin/")
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
        wheel = make_wheel(home, ns.platform_tag, ns.out_dir.resolve(), Path(tmp))
    size = wheel.stat().st_size / 1e6
    print(f"built {wheel} ({size:.1f} MB)")


if __name__ == "__main__":
    main()
