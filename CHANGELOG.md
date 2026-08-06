# Changelog

All notable changes to chefe are documented here.

The format follows Keep a Changelog, and releases are cut from the version in `pyproject.toml`.

## 0.0.27

### Fixed

- User-facing errors now print to stderr instead of stdout. A failure written to stdout is
  invisible to anyone who redirects it (`chefe install > log`) and indistinguishable from output
  to a CI step or an agent that captures the stream, so a refused install could read as a
  finished one. The exit status was and remains 1 for every one of these, and the whole command
  surface is now covered by a test that asserts both halves at once.

- A command run in a directory with no manifest reports `chefe.toml not found` with the way out
  instead of crashing with a raw `FileNotFoundError` traceback. `chefe install` and `chefe sync`
  hashed the manifest before anything checked that a workspace was there, so every read of the
  manifest now raises the same actionable error.

## 0.0.26

### Fixed

- Editing `chefe.toml` no longer deletes `.chefe/pixi.lock`. The lock was removed whenever the
  compiled manifest changed, which took the whole workspace down until someone noticed and
  re-resolved, and every command in the meantime failed with a confusing missing lock error.
  Chefe now writes a `.resolution-stale` marker beside the lock instead, so the environment
  keeps working and the drift is reported rather than enforced.

- `chefe shell` no longer freezes the terminal. The subshell was launched through the seam that
  pipes output so chefe can retain a copy, which left an interactive shell drawing its prompt and
  its line editor into a pipe while the terminal stayed in raw mode. The shell now provisions the
  environment through the ordinary locked install, where lock drift is still diagnosed, and then
  receives the caller's own stdin, stdout, and stderr.

- Generated Pixi manifests use named rich platform entries for root and environment virtual
  packages. Current Pixi 0.72 accepts this documented replacement for deprecated
  `system-requirements` tables, so Chefe no longer emits a warning on every command.
- Generated manifests are replaced atomically under a workspace lock, so simultaneous Chefe
  commands cannot expose an empty or partly written `pixi.toml` to one another.
- `python-freethreading` now owns normal `[python.deps]` toolchain tables just like `python`, so
  a CPython 3.14t environment can declare Python packages without a false unknown-table error.

### Added

- Named environments can own tasks through `[envs.<name>.tasks]`. Chefe compiles them into the
  matching Pixi feature and `chefe run --env <name> <task>` resolves them without exposing the
  task in unrelated environments.
- chefe now reads its manifest from a `[tool.chefe]` table inside `pyproject.toml` when one is
  present, the way ruff, pytest, and hatch read their own `[tool.*]` tables, so a Python package
  keeps a single file. A `pyproject.toml` without `[tool.chefe]` (for example a monorepo root that
  drives chefe from a sibling `chefe.toml`) falls through to the standalone file unchanged.
- A `pyproject.toml` manifest inherits its dependencies from the PEP-standard tables rather than
  restating them: `[project.dependencies]` (PEP 508) becomes the runtime Python deps and
  `[dependency-groups]` `dev` (PEP 735, includes followed) becomes the dev-env deps. The package
  installs itself editable so it imports and its own deps resolve, like `pip install -e .`.
- `[tool.chefe.sources]` routes a named distribution to a provider without repeating its version:
  `conda` (with an optional `package` rename), `git`, or `path`. `[tool.chefe.conda]` carries
  conda-only native deps that have no PEP 508 form (the interpreter, system libs). The rest of
  `[tool.chefe]` (channels, tasks, env, overlays) passes through as before.
- The manifest writers (`add`/`remove`/`upgrade`) refuse to edit an embedded `[tool.chefe]`,
  pointing at the file to edit by hand, since a runtime dep belongs in `[project.dependencies]` and
  a tool in `[dependency-groups]`. Reading, `install`, and `run` work against either manifest.

## 0.0.24

### Fixed

- Bare `chefe upgrade` now updates Pixi-managed runtimes and Python packages, Node packages, and
  Cargo-installed tools in the selected environment within declared compatibility bounds. Pixi's
  all-package upgrade mode loosened intentional caps before solving, so a protected dependency
  such as `numpy <2.5` could be raised into a known `numba` conflict. Naming packages still
  explicitly raises those packages' manifest constraints.
- Generated Pixi manifests no longer use the deprecated `[system-requirements]` tables. Root
  virtual packages now live on named rich workspace platforms, matching environments reuse those
  names, and an environment with a different floor gets its own named platform variant. This
  removes repeated Pixi 0.72 warnings without losing per-environment CUDA constraints.
- `chefe add <pkg> -l nodejs` (and `-l rust`) now installs what it adds. The non-pixi path only
  wrote the manifest and recompiled, so the added package sat undeclared in the env and
  `chefe run <bin>` failed with command-not-found until a full `chefe install`. The add now
  provisions its toolchain right away (a node install, a cargo sync), matching how `pixi add`
  already installed conda and Python deps.
- `chefe remove <name>` no longer deletes a structural table that happens to share the removed
  package's name. Removing a package named like an environment wiped the whole `[envs.<name>]`
  table, and removing one named `dev` wiped `[dev]`. Structural tables and the children of the
  `envs`/`on` namespaces are now recognized as scopes, never runtime-keyed toolchain tables.
- `satisfied` accepts a pinless installed version (`None`, an editable or path install) and
  treats it as satisfied, instead of relying on every caller to narrow it first. This fixes the
  one strict-typing error in the cargo sync path.

## 0.0.23

### Fixed

- `chefe run <name> --help` (and `-h`) now reaches the task or executable instead of printing
  chefe run's own usage. cyclopts intercepts its help flags anywhere in a command's tokens, so
  the flag never made it into the leading-hyphen passthrough; the `run` command now registers
  with `help_flags=()` and forwards them itself. A help flag with no task name before it, as in
  `chefe run --help` or `chefe run -e serving --help`, still prints the run command's page, and
  `chefe --help` is untouched.
- A command no longer serves a stale generated env after `chefe.toml` is edited. `chefe run`
  (and any command that activates the env) read the already-compiled `.chefe/pixi.toml` and
  never noticed the manifest had changed, so a freshly added `[env]` var or dep silently did
  nothing until a manual `chefe sync`. Each sync now stamps the manifest's content digest, and
  activation recompiles first when that digest no longer matches, so an edit always takes effect.

### Changed

- A runtime `chefe global add` (`-l nodejs`, `-l python`, `-l rust`) against an environment that
  does not exist yet now provisions the matching runtime on demand (`pixi global install
  nodejs|python|rust`) before installing the package, instead of dead-ending with a pointer to
  `chefe global install`. So `chefe global add codex -l nodejs` is a single command on a clean
  machine, the conda `install`-verb create path extended to the runtime languages.

## 0.0.22

### Added

- `chefe completions [shell]` prints the shell-completion script for bash, zsh, or fish (it
  follows your `$SHELL` when you name none), so you can pipe it where your shell expects, e.g.
  `chefe completions zsh > ~/.zfunc/_chefe` or `eval "$(chefe completions)"`.
- `chefe tree --plan` turns the report into a dry run that lists what a `chefe install` would
  change, install the missing deps, update the drifted ones, and remove the explicit deps no
  longer declared, without touching the environment. Transitive installs stay the solver's.

### Fixed

- `chefe tree` and `chefe install` no longer crash with an `IndexError` when a crate's
  `.crates.toml` entry is missing its version field. The malformed record is skipped and the
  rest of the env still reports.
- The published version had drifted: `pyproject.toml` was left at 0.0.20 while the changelog
  documented 0.0.21, so the running `chefe --version` and the upgrade hints in error messages
  reported a stale number. The version is realigned here.

## 0.0.21

### Fixed

- `chefe global add` learned `-l/--language`, so `npm`, `cargo`, and `pypi` globals install
  through the env's own package manager instead of being rejected by `pixi global add`. conda
  stays the default. A runtime add against an env that has no runtime yet now points at
  `chefe global install` rather than failing on a missing binary.
- A conda `chefe global add` against a global env that does not exist yet creates it on demand
  (it picks `pixi global install` over `pixi global add`), instead of dead-ending with
  "Environment ... doesn't exist".
- Workspace discovery walks up from the current directory to the nearest `chefe.toml`, the way
  git finds `.git`, so chefe works from any subdirectory of a workspace and only reports the
  manifest missing when none exists above.

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
