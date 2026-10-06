# hello-nim

A Python package whose core is written in Nim, built with `nimlang`'s hatch hook:

- `src/hello_nim/nimcore.nim` becomes the extension module `hello_nim.nimcore` (via nimpy)
- `src/hello_nim/hello_nim_cli.nim` becomes the `hello_nim_cli` executable

```sh
uv run nimlang sync          # install the Nim deps pinned in nimlang.lock (nimpy)
uv build                     # wheel tagged py3-none-<platform>
NIMLANG_TARGET=aarch64-macos uv build   # cross-build a macOS arm64 wheel from Linux
```
