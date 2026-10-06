# uv add nimlang

Use [Nim](https://nim-lang.org) in a Python project with nothing but uv.

`nimlang` is a Python package that ships the Nim compiler in its wheels and compiles C through
`zig cc` from the [ziglang](https://pypi.org/project/ziglang/) package, so you need no system
Nim and no C compiler.

> Status: early, first release on [PyPI](https://pypi.org/project/nimlang/). See [docs/design.md](docs/design.md) for what works
> and what is planned.

AI disclosure: this project is mostly vibed. Currently [level 7](https://www.visidata.org/blog/2026/ai/#level-6%3A-bots-coded%2C-human-understands-mostly) on visidata AI scale: Human specced, bots coded.

## Try it: a Python project with a Nim function

```sh
uv init uv-add-nimlang-demo && cd uv-add-nimlang-demo
uv add nimlang
uv run nimlang add nimpy            # Nim deps go in [tool.nimlang] in pyproject.toml
uv run nimlang info                 # bundled Nim and zig, and the project's Nim deps
```

`nimfib.nim`, write a function in Nim:

```nim
import nimpy

proc fib(n: int): int {.exportpy.} =
  if n < 2: n else: fib(n - 1) + fib(n - 2)
```

`fast.py`, use it in Python:

```python
from nimfib import fib  # the extension module built from nimfib.nim
```

`slow.py`, the same function in Python:

```python
def fib(n):
    return n if n < 2 else fib(n - 1) + fib(n - 2)
```

Build the extension and compare them with `timeit`:

```sh
uv run nimlang build-ext nimfib.nim   # writes nimfib.<python-tag>.so (.pyd on Windows) next to it
uv run python -m timeit -s "from slow import fib" "fib(30)"   # 2 loops, best of 5: 135 msec per loop
uv run python -m timeit -s "from fast import fib" "fib(30)"   # 20 loops, best of 5: 10.6 msec per loop
```

## Ship Nim code in a Python package

```toml
[build-system]
requires = ["hatchling", "nimlang"]
build-backend = "hatchling.build"

[tool.hatch.build.hooks.nimlang]
extensions = ["src/mypkg/nimcore.nim"]  # importable as mypkg.nimcore
binaries = ["src/mypkg/mytool.nim"]     # installed as the `mytool` command

[tool.nimlang]
dependencies = ["nimpy"]
```

`uv build` produces a `py3-none-<platform>` wheel that works on every CPython 3 version.
On Linux it is manylinux-compliant out of the box, and `NIMLANG_TARGET=aarch64-macos uv build`
cross-builds for other platforms. See [examples/hello-nim](examples/hello-nim).

> disclosure: have not tested this yet

## Building nimlang wheels

```sh
python scripts/make_wheels.py --nim-dist nim-2.2.6-linux_x64.tar.xz --platform-tag manylinux_2_17_x86_64
```

CI builds them for Linux (x86_64, aarch64), macOS (arm64, x86_64) and Windows x86_64, and
publishes to PyPI when a `v*` tag is pushed. For development without a bundled Nim, set
`NIMLANG_NIM_HOME` or put `nim` on `PATH`.

What's next: [ROADMAP.md](ROADMAP.md).
