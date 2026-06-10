# Changelog

All notable changes to chefe are documented here.

The format follows Keep a Changelog, and releases are cut from the version in `pyproject.toml`.

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
