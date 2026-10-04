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

## Optional nimporter integration (after the first release)

nimlang does not depend on nimporter for now. The idea is an optional `nimlang[import]`
extra that gives a dev-time `import foo` for `foo.nim`, compiled through nimlang (zig cc and
the project's `[tool.nimlang]` dependencies). It would likely be a maintained fork of
nimporter, with fixes also sent upstream. Problems with upstream today:

- The latest real release is 1.1.0 (November 2021). The 2.0.0 uploaded in March 2022 was a
  release candidate and was yanked, and master has carried the unreleased 2.0 since July 2023.
- It doesn't declare setuptools, so `import nimporter` fails in a fresh uv venv on Python 3.12.
- It pulls in about 28 packages, including cookiecutter and icecream.
- It compiles with `nimble c --accept` against the global `~/.nimble`, not a project's
  dependencies.

## Other items

- **Lock file for Nim dependencies:** record resolved versions/commits of `[tool.nimlang]`
  dependencies next to uv.lock.
- **Native `zigcc` shim on Windows:** a tiny executable instead of the `.cmd` file.
- **`nimlang init`:** scaffold a mixed Python/Nim project (nimpy module, build hook, tests).
- **Editor support:** point nimsuggest/nimlangserver at the venv's Nim and the project's
  dependency paths.
- **More platforms:** musllinux, Windows arm64, Linux armv7.
