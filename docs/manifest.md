# The manifest

Everything lives in one `chefe.toml`. The header configures the workspace, `[deps]` and the per-ecosystem tables declare packages, and platform overlays and named environments compose on top.

## Workspace

```toml
[workspace]
name     = "my-project"
platforms = ["osx-arm64", "linux-64"]
channels = ["conda-forge", "nvidia"]
dotenv   = true                 # read .env into the environment, on by default
```

## Dependencies

The bare `[deps]` table is **conda**, the default source. A bare string is a version spec, and `*` means any.

```toml
[deps]
python = ">=3.11"
nodejs = ">=22"
ripgrep = "*"
pueue  = ">=4"
```

## PyPI

PyPI packages are resolved by pixi-via-`uv` into the **same** environment. `[pypi]` holds settings, `[pypi.deps]` the packages, and `[pypi.indexes]` named extra indexes.

```toml
[pypi]
index-strategy = "unsafe-best-match"

[pypi.indexes]
pytorch = "https://download.pytorch.org/whl/cu124"

[pypi.deps]
torch = { version = ">=2.6", index = "pytorch" }
ruff  = ">=0.6"
```

## Other ecosystems

Every other ecosystem is explicit, so nothing is inferred.

```toml
[cargo.deps]
bookokrat = "*"

[npm.deps]
prettier = ">=3"
"@tobilu/qmd" = "*"
```

!!! tip "Runtimes are ensured automatically"
    Each ecosystem needs its language runtime to install and run, so chefe adds it from
    conda-forge when missing. `[pypi.deps]` ensures `python`, `[npm.deps]` ensures `nodejs`,
    `[cargo.deps]` ensures `rust`, and `[gem.deps]` ensures `ruby`. Declare your own pinned
    `python` (or others) in `[deps]` and chefe leaves it alone. This holds per environment too,
    so a `no-default` env that uses `[pypi.deps]` still gets its own `python`.

## System requirements

The conda virtual-package floor used for cross-platform solving, not a module-load.

```toml
[system]
cuda = "13.0"
```

## Environment variables

Static variables applied when the environment activates. `.env` is also read by default, toggled with `dotenv` in the header.

```toml
[env]
LOG_LEVEL = "info"
CUDA_MODULE_LOADING = "LAZY"
```

## Activation scripts

Shell scripts sourced when the environment activates, for setup that static env vars can't express (computed paths, library symlinks). They compile to pixi's `[activation] scripts`; a repo-root path keeps working from the generated `.chefe/`.

```toml
[activation]
scripts = ["scripts/activate.sh"]
```

## Platform overlays

Conditionally add deps per platform, and they compile to native pixi targets. Any scope nests under `[on.…]`.

```toml
[on.linux.deps]
cupy = ">=13"

[on.linux-aarch64.pypi.deps]
some-arm-wheel = "*"
```

## Named environments

Compose extra environments, like pixi features. `no-default = true` excludes the base deps, and `platforms` restricts the environment to where it can build (so a GPU env is skipped when solving on a laptop).

```toml
[envs.serving]
no-default = true
platforms  = ["linux-64", "linux-aarch64"]

[envs.serving.pypi.deps]
vllm = ">=0.6"
```

Install or inspect one with `chefe install serving` or `chefe tree serving`.

## Tasks

Named commands that run inside the environment, reached with `chefe run <task>`.

```toml
[tasks]
serve = { run = "python -m my_project.server", depends = ["build"] }
build = "python -m my_project.build"
```
