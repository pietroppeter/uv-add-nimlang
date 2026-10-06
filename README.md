# uv add nimlang

Use [Nim](https://nim-lang.org) in a Python project with nothing but uv.

`nimlang` is a Python package that ships the Nim compiler in its wheels and compiles C through
`zig cc` from the [ziglang](https://pypi.org/project/ziglang/) package, so you need no system
Nim and no C compiler.

> Status: early scaffold, not on PyPI yet. See [docs/design.md](docs/design.md) for what works
> and what is planned.

## Try it: a Python project with a Nim function

```sh
uv init nim-demo && cd nim-demo
uv add "nimlang @ git+https://github.com/pietroppeter/uv-add-nimlang"
uv run nimlang add nimpy            # Nim deps go in [tool.nimlang] in pyproject.toml
```

Write `fast.nim`:

```nim
import nimpy

proc fib(n: int): int {.exportpy.} =
  if n < 2: n else: fib(n - 1) + fib(n - 2)
```

Build it as an extension module and call it from Python:

```sh
uv run nimlang build-ext fast.nim   # writes fast.<python-tag>.so (.pyd on Windows) next to it
uv run python -c "import fast; print(fast.fib(30))"   # 832040
```

Until nimlang is on PyPI, the git install has no bundled Nim: put Nim 2.x on `PATH` (for example with
[choosenim](https://github.com/nim-lang/choosenim)) or point `NIMLANG_NIM_HOME` at an unpacked Nim
release. Once it is published, `uv add nimlang` brings Nim along and nothing else is needed.

## Use Nim in your project

```sh
uv add nimlang
uv run nim c -r hello.nim          # nim and nimble live in your venv
uv run nimlang add nimpy           # tracked in [tool.nimlang] in pyproject.toml
uv run nimlang build-ext fast.nim  # build a nimpy extension module next to fast.nim
uv run nimlang info                # bundled Nim version and where everything lives
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

## Building nimlang wheels

```sh
python scripts/make_wheels.py --nim-dist nim-2.2.6-linux_x64.tar.xz --platform-tag manylinux_2_17_x86_64
```

CI builds them for Linux (x86_64, aarch64), macOS (arm64, x86_64) and Windows x86_64, and
publishes to PyPI when a `v*` tag is pushed. For development without a bundled Nim, set
`NIMLANG_NIM_HOME` or put `nim` on `PATH`.

What's next: [ROADMAP.md](ROADMAP.md).
