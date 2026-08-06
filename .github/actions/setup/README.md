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

## Inputs

| input | default | when to change it |
|---|---|---|
| `python-version` | `3.14` | the project's `requires-python` floor differs |
| `chefe-version` | `>=0.0.27` | pin exactly when the build must survive a chefe release |
| `cache-key-files` | `pyproject.toml` | pass `chefe.toml` when that is the manifest, or both |
| `resolve` | `false` | only where the lock is deliberately not committed |

## On `resolve`

It defaults to false so a lock that no longer matches its manifest fails the build. Solving on
the runner instead would hide exactly the drift a committed lock exists to catch, and a green run
would then say nothing about whether the environment is reproducible anywhere else.

Committing `.chefe/pixi.toml`, `.chefe/pixi.lock` and `.chefe/.resolution-inputs` is what makes
that default correct. chefe treats a missing digest as drift, so the three travel together.
