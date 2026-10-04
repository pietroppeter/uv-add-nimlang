# Roadmap

Ideas for after the first release, roughly in priority order.

## Choose the Nim version per project

Today each nimlang release bundles one Nim version. The goal is for a project to pick its Nim
(say 2.0 for an older codebase) while keeping `uv add nimlang` as the only setup step.

Two ways to get there:

- **Compiler package (preferred).** Ship Nim in a separate `nimlang-nim` package whose
  version is the Nim version, with `nimlang` depending on it. A project pins Nim with
  `uv add "nimlang-nim==2.0.16"` and uv.lock records it. This was prototyped in commit
  `d81715d` on the scaffold branch: it built a 9.4 MB `nimlang-nim` wheel per platform, and
  switching a project from Nim 2.2.6 to 2.2.4 worked locally.
- **Download on demand.** `nim = "2.0"` in `[tool.nimlang]`, with nimlang downloading and
  caching that compiler on first use, like `uv python`. This is more flexible, but sits
  outside uv.lock and needs network access at first use.

## Other items

- **Lock file for Nim dependencies:** record resolved versions/commits of `[tool.nimlang]`
  dependencies next to uv.lock.
- **Native `zigcc` shim on Windows:** a tiny executable instead of the `.cmd` file.
- **`nimlang init`:** scaffold a mixed Python/Nim project (nimpy module, build hook, tests).
- **Editor support:** point nimsuggest/nimlangserver at the venv's Nim and the project's
  dependency paths.
- **More platforms:** musllinux, Windows arm64, Linux armv7.
- **Import hook:** an optional dev-time `import foo` for `foo.nim`, the convenience nimporter
  offered, built on nimlang's toolchain.
