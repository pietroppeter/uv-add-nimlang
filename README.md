# uv add nimlang

Use [Nim](https://nim-lang.org) in a Python project with nothing but uv.

`nimlang` is a Python package that ships the Nim compiler in its wheels and compiles C through
`zig cc` from the [ziglang](https://pypi.org/project/ziglang/) package, so you need no system
Nim and no C compiler.

> AI disclosure: this project is mostly vibed. Currently [level 7](https://www.visidata.org/blog/2026/ai/#level-6%3A-bots-coded%2C-human-understands-mostly) on visidata AI scale: Human specced, bots coded.

> Status: alpha. Ideas for evolution: [ROADMAP.md](ROADMAP.md).

## Try it: a Python project with a Nim function

```sh
uv init uv-add-nimlang-demo && cd uv-add-nimlang-demo
uv add nimlang
uv run nimlang add nimpy            # Nim deps go in [tool.nimlang] in pyproject.toml
uv run nimlang info                 # bundled Nim and zig, and the project's Nim deps
```

`slow.py`, you have a slow function in Python:

```python
def fib(n):
    return n if n < 2 else fib(n - 1) + fib(n - 2)
```

`fast.nim`, you write it in Nim:

```nim
import nimpy

proc fib(n: int): int {.exportpy.} =
  if n < 2: n else: fib(n - 1) + fib(n - 2)
```

`fast.py`, and import it in Python (it needs the extensione module built):

```python
from fast import fib
```

Build the extension module and compare slow and fast versions with `timeit`:

```sh
uv run nimlang build-ext fast.nim   # writes nimfib.<python-tag>.so (.pyd on Windows) next to it
uv run python -m timeit -s "from slow import fib" "fib(30)"   # 2 loops, best of 5: 135 msec per loop
uv run python -m timeit -s "from fast import fib" "fib(30)"   # 20 loops, best of 5: 10.6 msec per loop
```

## How Nim and Nim dependencies are provided

**The Nim compiler** comes inside the nimlang wheel for your platform (Linux x86_64/aarch64,
macOS arm64/x86_64, Windows x86_64). Each nimlang release bundles one Nim version, currently
2.2.6, along with atlas. `uv run nim` runs it with
zig cc as the C compiler and with the project's Nim dependencies on the path:

```sh
uv run nim --version         # 2.2.6
uv run nim c -r hello.nim
uv run nimlang info          # which Nim and zig are used, and the project's Nim deps
```

On other platforms nimlang uses `$NIMLANG_NIM_HOME` or a `nim` on `PATH`. Choosing the Nim
version per project is on the [roadmap](ROADMAP.md).

**The C compiler** is `zig cc` from the [ziglang](https://pypi.org/project/ziglang/) package,
installed as a regular dependency.

**Nim dependencies** are declared in `pyproject.toml`, next to the Python ones, and pinned in a
lock file, like uv does for Python packages:

```toml
[tool.nimlang]
dependencies = ["nimpy", "cligen >= 1.7"]
```

```sh
uv run nimlang add nimpy     # adds it to [tool.nimlang] and syncs
uv run nimlang remove nimpy  # removes it and syncs
uv run nimlang sync          # installs exactly what nimlang.lock pins
uv run nimlang lock          # resolves again to the newest allowed versions
```

- `nimlang.lock` records the git URL and commit of every package, including transitive ones.
  Commit it, so every checkout and every wheel build uses the same code.
- Packages are cloned with the bundled [atlas](https://github.com/nim-lang/atlas) into
  `.nimlang/` (git-ignored), so git is needed. Builds through nimlang see only those packages,
  never `~/.nimble`.
- nimlang drives atlas for you: there is no `atlas` command, and nimble is not shipped.
  `[tool.nimlang]` and `nimlang.lock` are the only places dependencies are managed.

## Ship Nim code in a Python package

> disclosure: have not tested this yet

```toml
[build-system]
requires = ["hatchling", "nimlang"]
build-backend = "hatchling.build"

[tool.hatch.build.hooks.nimlang]
extensions = ["src/mypkg/nimcore.nim"]  # importable as mypkg.nimcore
binaries = ["src/mypkg/mytool.nim"]     # installed as the `mytool` command
# strip = false                         # keep debug symbols (stripped by default)

[tool.nimlang]
dependencies = ["nimpy"]
```

`uv build` produces a `py3-none-<platform>` wheel that works on every CPython 3 version.
On Linux it is manylinux-compliant out of the box, and `NIMLANG_TARGET=aarch64-macos uv build`
cross-builds for other platforms. See [examples/hello-nim](examples/hello-nim).

## Building nimlang wheels

```sh
python scripts/make_wheels.py --nim-dist nim-2.2.6-linux_x64.tar.xz --platform-tag manylinux_2_17_x86_64
```

CI builds them for Linux (x86_64, aarch64), macOS (arm64, x86_64) and Windows x86_64, and
publishes to PyPI when a `v*` tag is pushed.

## Escape hatch: your own C compiler

If zig cc can't build something, `NIMLANG_CC=system` makes Nim use its default C compiler
(gcc, clang or MSVC) instead. It is not tested in CI and cannot cross-compile, so it can't
build wheels on Linux, where they always target glibc 2.17.
