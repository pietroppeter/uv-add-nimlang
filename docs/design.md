# nimlang: design notes

Goal: `uv add nimlang` is all a Python project needs to start using Nim.

- `nim` and `nimble` work inside the project (`uv run nim c -r app.nim`), with no system C compiler.
- Nim dependencies are declared and tracked in `pyproject.toml` (`nimlang add nimpy`).
- A package can ship Nim-built extension modules and executables in ordinary wheels,
  with `nimlang` as a build dependency.

## What was verified

All of this ran in a Linux x86_64 sandbox with no Nim install, using Nim 2.2.6 and the
`ziglang` 0.16.0 wheel from PyPI:

| Check | Result |
|---|---|
| Nim compiles with `zig cc` as its C compiler (`--cc:clang --clang.exe:<zigcc shim>`) | works |
| Cross-compiling a Nim program to Windows x64, macOS arm64 and Linux arm64 from Linux | works (binaries not run on those OSes yet) |
| nimpy extension module built with zig cc, imported from Python | works |
| Same extension built against glibc 2.17 (`-target x86_64-linux-gnu.2.17`) | max symbol version GLIBC_2.14, so manylinux_2_17 compliant |
| Nim distribution repackaged into a `nimlang` platform wheel | 9.4 MB wheel (26 MB unpacked) |
| `uv add nimlang` (from that wheel) then `uv run nim c -r hello.nim` | works |
| `nimlang add nimpy` → nimble installs into `.nimlang/`, then `nimlang build-ext` | works |
| `examples/hello-nim`: `uv build` with the hatch hook | `py3-none-manylinux_2_17_x86_64` wheel with extension + CLI |
| That one wheel on CPython 3.11 and 3.13 | works on both: nimpy has no compile-time libpython dependency |
| `NIMLANG_TARGET=aarch64-macos uv build`, `NIMLANG_TARGET=x86_64-windows-gnu uv build` from Linux | correct Mach-O / PE files and wheel tags |

## Architecture

### 1. Two packages: `nimlang` and `nimlang-nim`

- **`nimlang`** is pure Python (the CLI, the zig cc wiring, the build hook) with its own
  version numbers. It depends on `nimlang-nim` and `ziglang`.
- **`nimlang-nim`** is the compiler, the same trick as
  [ziglang](https://pypi.org/project/ziglang/): platform wheels holding a Nim distribution
  (`bin/`, `lib/`, `config/`) under `nimlang_nim/nim/`, versioned exactly like Nim.
  `scripts/make_nim_wheel.py` builds them; only `nim`, `nimble`, `nimsuggest`, `nimpretty`,
  `nimgrep` and `atlas` (plus DLLs on Windows) are kept from `bin/`. For manylinux tags it
  checks the binaries' glibc symbol versions against the tag.

So each project picks its Nim the way it picks any dependency, and uv.lock pins it:

```sh
uv add nimlang                        # latest Nim
uv add "nimlang-nim==2.2.4"           # this project stays on Nim 2.2.4
```

Several Nim versions can be published side by side (add them to `NIM_VERSION` in CI), and
different projects on one machine use different ones. A repackaging fix for the same Nim
uses a post release (`2.2.6.post1`).

Where the binaries come from: official Nim release builds where they exist (Linux x86_64,
Windows x86_64), built from the source release elsewhere (macOS arm64 and x86_64 natively;
Linux aarch64 linked against glibc 2.17 with zig cc).

Lookup order for the compiler: `$NIMLANG_NIM_HOME`, the `nimlang-nim` package, then a `nim`
on `PATH` (choosenim-style proxies are resolved with `nim dump`). `nimlang info` shows which
Nim version is in use.

`ziglang` is a regular dependency, so the C compiler arrives with the same `uv add`.

### 2. zig cc wiring

Nim calls its C compiler as a single executable, so it cannot be pointed at `zig cc` directly.
nimlang writes a two-line shim (`zigcc` shell script, `zigcc.cmd` on Windows) into the user
cache, keyed by the zig path of the environment, and passes
`--cc:clang --clang.exe:<shim> --clang.linkerexe:<shim>`.

Flags are inserted right after the Nim command, and only for commands that run the C
compiler (`c`, `cpp`, `r`, ...). `nim e` is left alone: nimble evaluates `.nimble` files
with it and NimScript sees every command-line argument (injecting there broke nimble).
`NIMLANG_CC=system` opts out and uses Nim's default compiler.

Cross-compilation is the same mechanism plus `--os/--cpu` and `-target <zig triple>`.

### 3. Nim dependencies

```toml
[tool.nimlang]
dependencies = ["nimpy", "cligen >= 1.7"]
```

`nimlang add/remove` edit this table (format-preserving, via tomlkit) and `nimlang sync`
runs the bundled nimble with `--nimbleDir:.nimlang/nimble`. Compiles through nimlang get
`--noNimblePath` plus one `--path` per installed package, so a build sees exactly the
project's dependencies and nothing from `~/.nimble`.

### 4. Distributing Nim code in Python packages

A hatchling build hook ships with nimlang (registered through the `hatch` entry point):

```toml
[build-system]
requires = ["hatchling", "nimlang"]
build-backend = "hatchling.build"

[tool.hatch.build.hooks.nimlang]
extensions = ["src/mypkg/nimcore.nim"]  # -> mypkg.nimcore (nimpy)
binaries = ["src/mypkg/mytool.nim"]     # -> `mytool` on PATH
```

- Missing `[tool.nimlang]` dependencies are synced before compiling.
- Extensions use the plain `.so`/`.pyd` suffix and wheels are tagged `py3-none-<platform>`:
  one wheel per platform covers every CPython 3.
- On Linux the default target pins glibc 2.17, so native wheels are manylinux-compliant
  without a manylinux container.
- `NIMLANG_TARGET` (or `target =` in the hook config) cross-builds: a single Linux CI job can
  produce wheels for every platform. No cibuildwheel needed.
- Editable installs (`uv sync`) build extensions in place next to the sources; add
  `[tool.uv] cache-keys` on `*.nim` so uv rebuilds when they change (see the example).

### nimpy and nimporter

nimpy is the core dependency for extensions and works well with this approach. nimporter's
last release was 1.1.0 in March 2022; it compiles at import time or via setuptools and
expects a C compiler on the user's machine, which is the problem nimlang removes. nimlang does
not depend on it. Its "import .nim files directly" convenience could be added later as an
optional dev-time import hook.

## Decisions (2026-10-04)

1. **Nim binaries:** official release builds where they exist, source builds elsewhere.
2. **Versioning:** `nimlang` has its own versions; the compiler is versioned like Nim in
   `nimlang-nim`, which also lets each project choose its Nim version.
3. **Nim dependencies:** `[tool.nimlang]` in pyproject.toml. A lock file is not implemented
   yet; the likely route is recording resolved versions/commits next to `uv.lock`.
4. **Build integration:** the hatchling hook (a dedicated PEP 517 backend is more work for
   little gain right now).
5. **PyPI:** reserve `nimlang` and `nimlang-nim` with an early release, published from CI
   through trusted publishing when a `v*` tag is pushed.

## Known gaps and next steps

- A tiny native `zigcc` executable per platform would be more robust than the `.cmd` shim on
  Windows.
- **Lock file** for Nim dependencies (see fork 3).
- **`nimlang init`** to scaffold a mixed Python/Nim project, and editor support (nimsuggest
  from the venv).
- Building from an sdist needs network access for the nimble dependencies, as with any
  nimble-based build.
