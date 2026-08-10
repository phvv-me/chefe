# `chefe/setup`

One composite action so a workflow says what it wants run rather than how to build an
environment. It installs uv and chefe, restores the solver and the solved environment from
cache, and installs.

```yaml
steps:
  - uses: actions/checkout@v6
  - uses: phvv-me/chefe/.github/actions/setup@main
  - run: chefe run lint
  - run: chefe run typecheck
  - run: chefe run test
```

That replaces roughly twenty lines per workflow, and more importantly it puts the uv version,
the action versions, the cache paths and the cache key in one place instead of five. A repository
that hand-rolls those drifts from the others quietly, which is how one of ours ended up caching
an environment it could not rebuild.

Repositories that declare their development dependencies to uv rather than to chefe use the
same action in `uv` mode, so the tool versions and the checkout still live in one place:

```yaml
  - uses: phvv-me/chefe/.github/actions/setup@main
    with:
      mode: uv
      extras: dev sql
  - run: uv run ruff check .
```

## Inputs

| input | default | when to change it |
|---|---|---|
| `mode` | `chefe` | `uv` for a repository without a `[tool.chefe]` manifest |
| `extras` | `dev` | `uv` mode only, space separated, becomes repeated `--extra` |
| `python-version` | `3.14` | the project's `requires-python` floor differs |
| `chefe-version` | `>=0.0.27` | pin exactly when the build must survive a chefe release |
| `cache-key-files` | `{chefe.toml,pyproject.toml}` | narrow it when only one manifest shapes the environment |
| `cache-paths` | empty | newline-separated project build directories worth restoring |
| `resolve` | `false` | only where the lock is deliberately not committed |

Cache keys include the operating system, architecture, Python version, Chefe version, and manifest
content. This prevents a matrix entry or tool upgrade from restoring an incompatible environment.
The action pins its own upstream actions by commit while keeping readable version comments beside
them.

## On `resolve`

It defaults to false so a lock that no longer matches its manifest fails the build. Solving on
the runner instead would hide exactly the drift a committed lock exists to catch, and a green run
would then say nothing about whether the environment is reproducible anywhere else. In `chefe`
mode it becomes `chefe install --resolve`, and in `uv` mode it drops `--frozen` from `uv sync`.

Committing `.chefe/pixi.toml`, `.chefe/pixi.lock` and `.chefe/.resolution-inputs` (`chefe` mode)
or `uv.lock` (`uv` mode) is what makes that default correct. A repository that deliberately does
not commit its lock sets `resolve: true` so its environment solves fresh instead of failing.
