# hello-nim

A test package for nimlang's hatch hook: CI builds it with the nimlang wheels of the same run,
natively on each OS and cross-compiled from Linux, then installs and runs it. For a user-facing
example see [uv-add-nimlang-lib-demo](https://github.com/pietroppeter/uv-add-nimlang-lib-demo).

- `src/hello_nim/nimcore.nim` becomes the extension module `hello_nim.nimcore` (via nimpy)
- `src/hello_nim/hello_nim_cli.nim` becomes the `hello_nim_cli` executable

```sh
uv run nimlang sync          # install the Nim deps pinned in nimlang.lock (nimpy)
uv build                     # wheel tagged py3-none-<platform>
NIMLANG_TARGET=aarch64-macos uv build   # cross-build a macOS arm64 wheel from Linux
```
