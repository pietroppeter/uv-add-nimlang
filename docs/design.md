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

### 1. The toolchain wheel (`nimlang`)

Same trick as [ziglang](https://pypi.org/project/ziglang/): a Python package whose platform
wheels contain a compiler distribution. `scripts/make_wheels.py` builds the pure-Python wheel
and injects a Nim distribution (`bin/`, `lib/`, `config/`) under `nimlang/nim/`, retagged as
`py3-none-<platform>`. Only `nim`, `nimble`, `nimsuggest`, `nimpretty`, `nimgrep` and `atlas`
are kept from `bin/`.

Lookup order for the compiler: `$NIMLANG_NIM_HOME`, the bundled distribution, then a `nim` on
`PATH` (choosenim-style proxies are resolved with `nim dump`). The fallbacks keep source
checkouts and CI usable before wheels are published.

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

## Design forks (recommended default first)

1. **Where Nim binaries come from.** *Recommended:* repackage the official release tarballs
   where they exist (Linux x86_64, Windows x86_64) and build from source with zig cc for the
   rest (macOS arm64/x86_64, Linux aarch64). Alternative: build every platform from source
   with zig in one Linux job (uniform and manylinux-controlled, but not the bits Nim users
   already trust).
2. **Versioning.** *Recommended:* mirror Nim's version (`nimlang 2.2.6` ships Nim 2.2.6), with
   `.postN` for packaging fixes, like ziglang. Users pin Nim with `uv add nimlang==2.2.6`.
3. **Source of truth for Nim deps.** *Recommended:* `[tool.nimlang]` in pyproject.toml (one
   file for Python users). Alternative: a regular `.nimble` file that nimlang reads. A lock
   file is not implemented yet; the likely route is recording resolved versions/commits next
   to `uv.lock`.
4. **Build integration.** *Recommended:* the hatchling hook (small, reuses hatch's wheel
   logic). Alternative: a dedicated PEP 517 backend, more work for little gain right now.
5. **PyPI name.** `nimlang` is free on PyPI today (checked 2026-10-04). Worth reserving with
   a first release soon.

## Known gaps and next steps

- **macOS and Windows** pass CI (unit tests, example wheel built natively, installed and run)
  using a Nim from PATH; the bundled-wheel path is so far only exercised on Linux. A tiny
  native `zigcc` executable per platform would be more robust than the `.cmd` shim on Windows.
- **Release pipeline.** A workflow that downloads/builds Nim per platform, runs
  `make_wheels.py` and publishes to PyPI.
- **Lock file** for Nim dependencies (see fork 3).
- **`nimlang init`** to scaffold a mixed Python/Nim project, and editor support (nimsuggest
  from the venv).
- Building from an sdist needs network access for the nimble dependencies, as with any
  nimble-based build.
