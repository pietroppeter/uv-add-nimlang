import json
import os
import shutil
import subprocess

import pytest
import tomlkit

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


@pytest.mark.parametrize(
    "req, nimble",
    [
        ("nimpy", "nimpy"),
        ("nimpy >= 0.2.0", "nimpy >= 0.2.0"),
        ("nimpy#head", "nimpy#head"),
        ("nimpy@#head", "nimpy#head"),
        ("nimpy@0.2.0", "nimpy == 0.2.0"),
        ("nimpy@>=0.2", "nimpy >=0.2"),
        ("https://github.com/yglukhov/nimpy", "https://github.com/yglukhov/nimpy"),
    ],
)
def test_nimble_requirement(req, nimble):
    assert _project.nimble_requirement(req) == nimble


def test_path_args_from_atlas_cfg(project):
    ws = _project.workspace(project)
    ws.mkdir()
    (ws / "nim.cfg").write_text(
        "############# begin Atlas config section ##########\n--noNimblePath\n"
        '--path:"deps/nimpy"\n--path:"deps/jsony/src"\n'
        "############# end Atlas config section   ##########\n"
    )
    installed = _project.installed_packages(project)
    assert installed == {"nimpy": ws / "deps" / "nimpy", "jsony": ws / "deps" / "jsony" / "src"}
    args = _project.path_args(project)
    assert args[0] == "--noNimblePath" and len(args) == 3


def _fake_atlas(calls, commit, sep="/"):
    """Stand-in for atlas: `install` checks out nimpy, `pin`/`rep` write their files."""

    def run(root, args):
        calls.append(args[0])
        ws = _project.workspace(root)
        repo = ws / "deps" / "nimpy"
        if args[0] in ("install", "rep"):
            repo.mkdir(parents=True, exist_ok=True)
            (repo / "nimpy.nimble").write_text('version = "0.2.1"\n')
            (ws / "nim.cfg").write_text('--noNimblePath\n--path:"deps/nimpy"\n')
            heads[repo] = commit
        if args[0] == "pin":
            items = {
                "nimpy": {"dir": "$deps/nimpy", "url": "https://x/nimpy", "commit": commit, "version": ""}
            }
            (ws / "atlas.lock").write_text(json.dumps({"items": items}))
        return 0

    heads = {}
    return run, heads


@pytest.mark.parametrize("sep", ["/", "\\"])
def test_lock_and_sync(project, monkeypatch, sep):
    calls = []
    run, heads = _fake_atlas(calls, "abc123", sep)
    monkeypatch.setattr(_project, "run_atlas", run)
    monkeypatch.setattr(_project, "_git_head", lambda path: heads.get(path))
    _project.add_deps(project, ["nimpy@#head"])

    assert _project.sync(project) == 0
    assert calls == ["install", "pin"]
    manifest = (_project.workspace(project) / _project.MANIFEST).read_text()
    assert manifest == 'requires "nimpy#head"\n'
    lock = tomlkit.parse((project / _project.LOCK_FILE).read_text()).unwrap()
    assert lock["requires"] == ["nimpy@#head"]
    assert lock["package"] == [
        {"name": "nimpy", "version": "0.2.1", "url": "https://x/nimpy", "commit": "abc123"}
    ]

    # Up to date: nothing runs. Fresh checkout: the lock is replayed, not resolved.
    calls.clear()
    assert _project.sync(project) == 0 and calls == []
    heads.clear()
    assert _project.sync(project) == 0 and calls == ["rep"]

    # A replay that lands on another commit is an error.
    calls.clear()
    heads.clear()
    monkeypatch.setattr(_project, "run_atlas", lambda root, args: 0)
    with pytest.raises(NimlangError, match="nimpy"):
        _project.sync(project)

    # Removing every dependency removes the lock file.
    _project.remove_deps(project, ["nimpy"])
    assert _project.sync(project) == 0
    assert not (project / _project.LOCK_FILE).exists()


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
    assert hatch_hook.platform_tag("x86_64-windows-gnu") == "win_amd64"


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


@pytest.mark.skipif(not _have_nim() or not shutil.which("git"), reason="needs Nim and git")
def test_atlas_lock_and_replay(project):
    """Real atlas, real network: resolve nimpy, then rebuild .nimlang from the lock alone."""
    _project.add_deps(project, ["nimpy"])
    assert _project.sync(project) == 0
    lock = tomlkit.parse((project / _project.LOCK_FILE).read_text()).unwrap()
    [nimpy] = lock["package"]
    assert nimpy["name"] == "nimpy" and len(nimpy["commit"]) == 40
    assert "nimpy" in _project.installed_packages(project)

    before = (project / _project.LOCK_FILE).read_text()
    shutil.rmtree(_project.workspace(project), onerror=_force_remove)
    assert _project.sync(project) == 0
    assert _project._git_head(_project.workspace(project) / "deps" / "nimpy") == nimpy["commit"]
    assert (project / _project.LOCK_FILE).read_text() == before


def _force_remove(func, path, _exc):
    # git marks pack files read-only, which Windows refuses to delete.
    os.chmod(path, 0o700)
    func(path)
