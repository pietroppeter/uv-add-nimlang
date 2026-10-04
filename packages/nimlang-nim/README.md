# nimlang-nim

The [Nim](https://nim-lang.org) compiler, packaged as platform wheels for
[nimlang](https://github.com/pietroppeter/uv-add-nimlang). The package version is
the Nim version it contains, so a project picks its Nim with:

```sh
uv add nimlang "nimlang-nim==2.0.16"
```

Wheels are built by `scripts/make_nim_wheel.py`: official Nim release binaries
where they exist, source builds elsewhere.
