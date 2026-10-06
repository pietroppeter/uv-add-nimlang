# Roadmap

Ideas for after the first release, roughly in priority order.

## Choose the Nim version per project

Today each nimlang release bundles one Nim version. The goal is for a project to pick its Nim
(say 2.0 for an older codebase) while keeping `uv add nimlang` as the only setup step.

### Proposed: a `nimlang-nim` compiler package

Split the toolchain the way [ziglang](https://pypi.org/project/ziglang/) ships Zig:

| Package | Contents | Version |
|---|---|---|
| `nimlang` | pure Python: CLI, zig cc wiring, hatch hook | its own |
| `nimlang-nim` | platform wheels with a Nim distribution (`nim`, `atlas`, `lib/`) | exactly Nim's, `.postN` for repackaging fixes |

`nimlang` depends on `nimlang-nim>=2.0`. A project that does nothing gets the newest Nim; one
that cares pins it like any other dependency, and uv.lock records it:

```sh
uv add nimlang
uv add "nimlang-nim==2.0.16"     # or "nimlang-nim~=2.0.0" to follow 2.0.x patches
```

This was prototyped in commits `d81715d` and `d42f48e` on the scaffold branch (reachable from
`refs/pull/1/head`): it built a 9.4 MB `nimlang-nim` wheel per platform, and switching a project
from Nim 2.2.6 to 2.2.4 worked locally. The prototype left these open:

- **Platforms without a wheel.** With a hard dependency, installing fails where `nimlang-nim`
  has no wheel (musllinux, Windows arm64, ...). Also publish a tiny `py3-none-any`
  `nimlang-nim` wheel with no compiler: installers prefer the platform wheel, so it is only
  picked where none exists, and nimlang falls back to `NIMLANG_NIM_HOME` or a `nim` on PATH.
- **Isolated build environments.** `[build-system] requires = ["nimlang"]` is resolved apart
  from uv.lock, so `uv build` would use the newest Nim, not the pinned one. A
  `[tool.nimlang] nim = "~=2.0.0"` setting would state the project's Nim in one place, checked by
  the CLI and the hatch hook, with a `nimlang use 2.0` command writing it plus the matching pins
  (the dependency and `[tool.uv] build-constraint-dependencies`).
- **Releases.** Nim and nimlang move at different speeds. In this repo, a separate workflow on
  `nim-v*` tags (e.g. `nim-v2.0.16`) builds and publishes one Nim version for every platform;
  `v*` tags release `nimlang` alone, now a single pure wheel. First versions: the current 2.2.x
  and 2.0.16 (the last 2.0). Roughly 40-50 MB per Nim version on PyPI.
- **Migration.** Released nimlang wheels keep their bundled Nim. The first pure release looks
  up `NIMLANG_NIM_HOME`, then `nimlang-nim`, then a Nim bundled inside nimlang (old wheels,
  local checkouts), then PATH.
- **Atlas.** `atlas` comes from the Nim distribution, so pinning Nim also pins atlas, and
  `nimlang sync` must keep working with the atlas of each published Nim version.

### Alternative: download on demand

`nim = "2.0"` in `[tool.nimlang]`, with nimlang downloading and caching that compiler on first
use, like `uv python`. This is more flexible (any version, nightlies), but sits outside uv.lock
and needs network access at first use. It could later cover versions without published wheels.

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

- **Keep locked versions when requirements change:** today adding a Nim dependency
  re-resolves all of them to the newest allowed versions (atlas has no "keep what's locked").
- **Native `zigcc` shim on Windows:** a tiny executable instead of the `.cmd` file.
- **`nimlang init`:** scaffold a mixed Python/Nim project (nimpy module, build hook, tests).
- **Editor support:** ship nimsuggest again (dropped from the wheel for now) and point
  nimlangserver / the VS Code Nim extension at it, the venv's Nim and the project's dependency paths.
- **More platforms:** musllinux, Windows arm64, Linux armv7.
