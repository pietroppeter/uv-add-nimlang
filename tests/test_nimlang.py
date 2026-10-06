import os
import subprocess
from pathlib import Path

import pytest

from nimlang import _project, _toolchain, cli
from nimlang._toolchain import NimlangError


@pytest.fixture
def project(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\nversion = "0.1.0"\n')
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.mark.parametrize(
    "req, name",
    [
        ("nimpy", "nimpy"),
        ("nimpy >= 0.2.0", "nimpy"),
        ("Nimpy@#head", "nimpy"),
        ("https://github.com/yglukhov/nimpy", "nimpy"),
        ("https://github.com/yglukhov/nimpy.git", "nimpy"),
    ],
)
def test_dep_name(req, name):
    assert _project.dep_name(req) == name


def test_add_and_remove_deps(project):
    assert _project.add_deps(project, ["nimpy"]) == ["nimpy"]
    assert _project.add_deps(project, ["cligen", "nimpy >= 0.2"]) == ["cligen", "nimpy >= 0.2"]
    text = (project / "pyproject.toml").read_text()
    assert 'name = "demo"' in text and "[tool.nimlang]" in text
    assert _project.remove_deps(project, ["nimpy"]) == ["cligen"]
    assert _project.read_deps(project) == ["cligen"]


def test_installed_packages_picks_highest_version(project):
    pkgs2 = _project.nimble_dir(project) / "pkgs2"
    for name in ["nimpy-0.2.0-abc", "nimpy-0.10.1-def", "cligen-1.7.0-123"]:
        (pkgs2 / name).mkdir(parents=True)
    installed = _project.installed_packages(project)
    assert installed["nimpy"].name == "nimpy-0.10.1-def"
    assert set(installed) == {"nimpy", "cligen"}
    args = _project.path_args(project)
    assert args[0] == "--noNimblePath" and len(args) == 3


def test_path_args_without_state(project):
    assert _project.path_args(project) == []
    assert _project.path_args(None) == []


def test_target_args():
    assert _toolchain.target_args("aarch64-macos") == [
        "--cpu:arm64",
        "--os:macosx",
        "--passC:-target aarch64-macos",
        "--passL:-target aarch64-macos",
    ]
    with pytest.raises(NimlangError):
        _toolchain.target_args("sparc-solaris")


def test_zigcc_shim(tmp_path, monkeypatch):
    monkeypatch.setattr(_toolchain, "_cache_dir", lambda: tmp_path)
    shim = _toolchain.zigcc_shim()
    assert str(_toolchain.zig_exe()) in shim.read_text()
    assert os.access(shim, os.X_OK)
    assert _toolchain.zigcc_shim() == shim


def test_cc_args_system(monkeypatch):
    monkeypatch.setenv("NIMLANG_CC", "system")
    assert _toolchain.cc_args() == []


def test_nim_args_injection(project, monkeypatch):
    monkeypatch.setattr(cli, "cc_args", lambda: ["--cc:clang"])
    assert cli.nim_args(["c", "-r", "x.nim"]) == ["c", "--cc:clang", "-r", "x.nim"]
    assert cli.nim_args(["--hints:off", "c", "x.nim"]) == ["--hints:off", "c", "--cc:clang", "x.nim"]
    # nimble evaluates .nimble files with `nim e`, which must see only its own arguments
    assert cli.nim_args(["e", "script.nims", "out.json"]) == ["e", "script.nims", "out.json"]
    assert cli.nim_args(["--version"]) == ["--version"]


def test_platform_tag():
    hatch_hook = pytest.importorskip("nimlang.hatch_hook")
    assert hatch_hook.platform_tag("x86_64-linux-gnu.2.17") == "manylinux_2_17_x86_64"
    assert hatch_hook.platform_tag("aarch64-linux-musl") == "musllinux_1_2_aarch64"
    assert hatch_hook.platform_tag("aarch64-macos") == "macosx_11_0_arm64"
    assert hatch_hook.platform_tag("x86_64-macos") == "macosx_10_13_x86_64"
    assert hatch_hook.platform_tag("x86_64-macos.12.3") == "macosx_12_3_x86_64"
    assert hatch_hook.platform_tag("x86_64-windows-gnu") == "win_amd64"


def test_pin_target():
    hatch_hook = pytest.importorskip("nimlang.hatch_hook")
    assert hatch_hook.pin_target("aarch64-macos") == "aarch64-macos.11.0"
    assert hatch_hook.pin_target("x86_64-macos") == "x86_64-macos.10.13"
    assert hatch_hook.pin_target("aarch64-macos.14.0") == "aarch64-macos.14.0"
    assert hatch_hook.pin_target("x86_64-linux-gnu.2.17") == "x86_64-linux-gnu.2.17"
    assert hatch_hook.pin_target(None) is None


def test_target_args_os_version():
    args = _toolchain.target_args("aarch64-macos.11.0")
    assert args[:2] == ["--cpu:arm64", "--os:macosx"]
    assert "--passC:-target aarch64-macos.11.0" in args


def _have_nim():
    try:
        _toolchain.nim_home()
        return True
    except NimlangError:
        return False


@pytest.mark.skipif(not _have_nim(), reason="no Nim distribution available")
def test_compile_and_run(project):
    from nimlang._build import build_binary

    (project / "hello.nim").write_text('echo "hello from nim"\n')
    exe = build_binary(project / "hello.nim")
    assert subprocess.run([str(exe)], capture_output=True, text=True).stdout == "hello from nim\n"


def test_nim_version(tmp_path):
    system = tmp_path / "lib" / "system"
    system.mkdir(parents=True)
    (system / "compilation.nim").write_text(
        "const\n  NimMajor* {.intdefine.}: int = 2\n  NimMinor* {.intdefine.}: int = 2\n"
        "  NimPatch* {.intdefine.}: int = 6\n"
    )
    assert _toolchain.nim_version(tmp_path) == "2.2.6"


def test_sync_runs_nimble_outside_the_project(project, monkeypatch):
    # uv unpacks sdists under a cache dir holding a non-repository .git file, which makes
    # git (called by nimble) fail anywhere below it.
    (project / ".git").write_text("not a gitdir\n")
    _project.write_deps(project, ["nimpy"])
    calls = []
    monkeypatch.setattr(_project, "run_nimble", lambda args, cwd=None: calls.append((args, cwd)) or 0)
    assert _project.sync(project) == 0
    ((args, cwd),) = calls
    assert project.resolve() not in Path(cwd).resolve().parents
    assert args[0] == f"--nimbleDir:{(project / '.nimlang' / 'nimble').resolve()}"
