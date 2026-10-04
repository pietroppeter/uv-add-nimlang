# uv add nimlang

Use [Nim](https://nim-lang.org) in a Python project with nothing but uv.

`nimlang` brings the Nim compiler as a wheel (`nimlang-nim`, versioned like Nim) and compiles C
through `zig cc` from the [ziglang](https://pypi.org/project/ziglang/) package, so you need no
system Nim and no C compiler.

> Status: early scaffold, not on PyPI yet. See [docs/design.md](docs/design.md) for what works
> and what is planned.

## Use Nim in your project

```sh
uv add nimlang
uv run nim c -r hello.nim          # nim and nimble live in your venv
uv run nimlang add nimpy           # tracked in [tool.nimlang] in pyproject.toml
uv run nimlang build-ext fast.nim  # build a nimpy extension module next to fast.nim
uv run nimlang info                # Nim version and where everything lives
uv add "nimlang-nim==2.2.4"        # pin this project to a specific Nim
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

## Building the compiler wheels

```sh
python scripts/make_nim_wheel.py --nim-dist nim-2.2.6-linux_x64.tar.xz --platform-tag manylinux_2_17_x86_64
```

CI builds them for Linux (x86_64, aarch64), macOS (arm64, x86_64) and Windows x86_64, and
publishes `nimlang` and `nimlang-nim` to PyPI when a `v*` tag is pushed. Until `nimlang-nim` is
on PyPI, point uv at locally built wheels with `UV_FIND_LINKS=dist`, or set `NIMLANG_NIM_HOME`.
