# uv add nimlang

Use [Nim](https://nim-lang.org) in a Python project with nothing but uv.

`nimlang` is a Python package that ships the Nim compiler in its wheels and compiles C through
`zig cc` from the [ziglang](https://pypi.org/project/ziglang/) package, so you need no system
Nim and no C compiler.

> Status: early scaffold, not on PyPI yet. See [docs/design.md](docs/design.md) for what works
> and what is planned.

## Use Nim in your project

```sh
uv add nimlang
uv run nim c -r hello.nim          # nim and nimble live in your venv
uv run nimlang add nimpy           # tracked in [tool.nimlang] in pyproject.toml
uv run nimlang build-ext fast.nim  # build a nimpy extension module next to fast.nim
uv run nimlang info                # where everything lives
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

For development without a bundled Nim, set `NIMLANG_NIM_HOME` or put `nim` on `PATH`.
