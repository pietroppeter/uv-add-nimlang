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

## nim and nimble available

Currently ships fixed nim and nimble versions

```sh
uv run nim --version # 2.2.6
uv run nimble --version # 0.20.1
```

## Nim dependencies

```sh
uv run nimlang add nimpy   # adds it to [tool.nimlang] in pyproject.toml and installs it
uv run nimlang sync        # installs exactly what nimlang.lock pins (commit it)
uv run nimlang lock        # resolves again to the newest allowed versions
```

Packages are fetched with [atlas](https://github.com/nim-lang/atlas) (bundled with Nim) into
`.nimlang/`, and builds through nimlang see only those, never `~/.nimble`.

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


