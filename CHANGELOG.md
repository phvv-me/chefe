# Changelog

All notable changes to chefe are documented here.

The format follows Keep a Changelog, and releases are cut from the version in `pyproject.toml`.

## 0.0.19

### Changed

- `chefe run` now prefers declared `[tasks]` entries, then falls through to executables on the
  activated environment `PATH`, so tools such as `vite`, `node`, and npm package binaries run
  directly without redundant task aliases. Both paths execute through `pixi run`, so the
  manifest's `[activation]` scripts and env vars always apply; a name that is neither a task
  nor an executable fails up front with guidance.
- `chefe global` now mirrors Pixi's everyday global environment operations with `add`,
  `remove`, and `list`, all defaulting to the workspace-named global env when an environment is
  needed.
- Python 3.14 is now the floor. The code uses PEP 695 generics and the native `type` alias for `Toml`, the `typing-extensions` dependency is gone, and deferred annotation evaluation replaces every `from __future__ import annotations`.
- `pull` is scope aware. A dep resolved for a concrete platform bumps the family selector that declares it (`[on.linux]` covers `target.linux-64`) instead of duplicating into a new table, the pixi `dev` feature folds back into `[dev]` rather than a fabricated `[envs.dev]`, and targets nested inside features fold into `[envs.<name>.on.<platform>]`.
- Backends fail loudly. A failing `pixi`, npm, or cargo command raises a clean error instead of printing green success, `chefe x` and `chefe shell` exit with the wrapped command's real code, and the pixi bootstrap reports installer failure.
- Toolchain tables validate against the union of their scope's and the root `[deps]`, so platform overlays no longer need a redundant local runtime pin. `[envs.dev]` is reserved alongside `[envs.default]`.
- `package.json` compiles from the toolchain merged for the installed env, so `[dev]`, platform overlay, and env-scoped nodejs deps reach the manifest. A nodejs spec carrying a source npm cannot express fails fast instead of degrading to `*`.
- Cargo sync pins `--environment`, reinstalls on version drift with `--force`, and expresses `locked`, `git`, `path`, `branch`, `tag`, and `rev` spec keys as their cargo flags.
- `activate.sh` renders from a packaged jinja2 template, omits the module block entirely when `[modules]` is empty so it never purges a job's loaded stack, and relaxes `set -u` around activation so nounset-unsafe conda hooks survive sourcing under `set -eu`.
- User-facing rich output goes through a t-string `markup()` processor that escapes every interpolated value, so package names can no longer inject markup.

### Added

- `workspace.dotenv` is wired. `chefe sync` generates a guarded loader that sources the workspace `.env` first in pixi activation.
- `Document.save` validates the manifest before writing, so no command can persist a file the next command would reject.

### Fixed

- `chefe upgrade` crashed with `KeyError: 'version'` on resolved `path`, `git`, and `url` specs, which carry no version to bump.
- `chefe tree` reported every installed Python dep as missing because pixi reports them as kind `pypi`.
- `chefe remove` stranded a toolchain table that had no direct `deps` key, wedging the workspace, and missed inline `deps = { ... }` tables.
- A stale `package.json` survived after the last nodejs dep was removed and kept reinstalling it.
- `no-default` envs no longer inherit base scopes in `tree`, and an env's own platform overlays now count as active scopes.
- Bare version pins in `chefe global` now render with an operator instead of concatenating into an invalid spec.

## 0.0.18

### Changed

- Typing is now mypy strict with `disallow_any_explicit`. The source carries no explicit `Any` or `object` annotations. A scoped override remains only for pydantic's plugin-generated `Any` on `extra="allow"` models.
- The docs adopt a shared design language built on Open Props tokens over mkdocs-material, with a legible app-icon used as both logo and favicon.
- `llms.txt` and `llms-full.txt` now generate from the english source via a post-build hook, so the i18n build no longer leaves them empty.
- CI actions updated to setup-uv v7, upload-pages-artifact v5, deploy-pages v5, and gh-release v3.

## 0.0.17

### Changed

- A manifest table with no matching `[deps]` package now fails with a self-contained message that names the running chefe and the `pip install -U chefe` fix (the usual cause is a table from a newer chefe), instead of a cryptic low-level error.
- Simplified the manifest error formatter so validators carry their own guidance, dropping the brittle match on message text.

## 0.0.16

### Added

- `[modules]` table (`name = "version"` pairs) baked into the generated `.chefe/activate.sh` as `module load name/version` for HPC hosts. Guarded by `command -v module`, so it no-ops off a cluster.

## 0.0.15

### Changed

- Require plumbum 2.0 and type-check its now-typed API (dropped the mypy ignore override for `plumbum.*`).

## 0.0.14

- Current released baseline.
