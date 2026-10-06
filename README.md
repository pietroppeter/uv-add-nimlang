# uv add nimlang

Use [Nim](https://nim-lang.org) in a Python project with nothing but uv.

`nimlang` is a Python package that ships the Nim compiler in its wheels and compiles C through
`zig cc` from the [ziglang](https://pypi.org/project/ziglang/) package, so you need no system
Nim and no C compiler.

[nimpy](https://github.com/yglukhov/nimpy) is the core Nim dependency: it is the binding
library that exports Nim procs to Python (`{.exportpy.}`) and lets Nim call Python. Every
Nim extension module built with nimlang uses it.

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

- Version constraints use atlas (nimble) syntax: the usual `==`, `>=`, `<` operators, `&` to
  combine them (`"nimib >= 0.3 & < 0.4"`), and `#head` or `#<commit>` for git refs
  (`"nimpy#head"`). A package name alone takes the newest release, which the lock then pins.
- `nimlang.lock` records the git URL and commit of every package, including transitive ones.
  Commit it, so every checkout and every wheel build uses the same code.
- Packages are cloned with the bundled [atlas](https://github.com/nim-lang/atlas) into
  `.nimlang/` (git-ignored), so git is needed. Builds through nimlang see only those packages,
  never `~/.nimble`.
- nimlang drives atlas for you: there is no `atlas` command, and nimble is not shipped.
  `[tool.nimlang]` and `nimlang.lock` are the only places dependencies are managed.

## Ship Nim code in a Python package

[uv-add-nimlang-lib-demo](https://github.com/pietroppeter/uv-add-nimlang-lib-demo) is a
minimal package built this way and published on PyPI as `nimlang-lib-demo`. Its users get
prebuilt wheels and need neither nimlang nor a compiler:

```sh
uv run --with nimlang-lib-demo python -m timeit -s "from nimlang_lib_demo.slow import fib" "fib(30)"
uv run --with nimlang-lib-demo python -m timeit -s "from nimlang_lib_demo.fast import fib" "fib(30)"
```

The setup is nimlang as a build requirement, plus its hatch hook pointing at the Nim files:

```toml
[build-system]
requires = ["hatchling", "nimlang"]
build-backend = "hatchling.build"

[tool.hatch.build.hooks.nimlang]
extensions = ["src/mypkg/fast.nim"]  # importable as mypkg.fast
# binaries = ["src/mypkg/mytool.nim"]  # installed as the `mytool` command

[tool.nimlang]
dependencies = ["nimpy"]
```

`uv build` produces a `py3-none-<platform>` wheel that works on every CPython 3 version.
On Linux it is manylinux-compliant out of the box, and `NIMLANG_TARGET=aarch64-macos uv build`
cross-builds for other platforms. The demo's CI builds all five platform wheels on one Linux
machine and tests each on its own OS.

## Related projects

- [nimpy](https://github.com/yglukhov/nimpy): Nim-Python bindings, the core dependency of
  every extension module (`nimlang add nimpy`).
- [nimpy_numpy](https://github.com/pietroppeter/nimpy-numpy): numpy array interop on top of
  nimpy, registered in the Nim package list (`nimlang add nimpy_numpy`).

Experiments in shipping Nim code to Python with nimlang:

- [uv-add-nimlang-lib-demo](https://github.com/pietroppeter/uv-add-nimlang-lib-demo): minimal
  package published on PyPI as `nimlang-lib-demo`, with prebuilt wheels for five platforms.
- [nimpy-numpy](https://github.com/pietroppeter/nimpy-numpy): its tests and benchmark build Nim
  extensions with nimlang (a Vandermonde matrix, standard vs contiguous fast path, against numpy).
- [not1d](https://github.com/pietroppeter/not1d): a minimal Nim port of
  [ot1d](https://github.com/stegua/ot1d) (1D optimal transport), as a test of a non-trivial
  algorithm and of the C++ backend (an optional build uses C++ pdqsort). Not on PyPI; install
  it from git.

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
