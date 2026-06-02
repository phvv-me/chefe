# The manifest

Everything lives in one `chefe.toml`. The header configures the workspace, `[deps]` and the per-ecosystem tables declare packages, and platform overlays and named environments compose on top.

## Header `[workspace]`

```toml
[workspace]
name     = "my-project"
platforms = ["osx-arm64", "linux-64"]
channels = ["conda-forge", "nvidia"]
dotenv   = true                 # read .env into the environment, on by default
```

## Conda deps `[deps]`

The bare `[deps]` table is **conda**, the default source. A bare string is a version spec, and `*` means any.

```toml
[deps]
python = ">=3.11"
nodejs = ">=22"
ripgrep = "*"
pueue  = ">=4"
```

## PyPI `[pypi]` and `[pypi.deps]`

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

## Other ecosystems `[<eco>.deps]`

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

## System requirements `[system]`

The conda virtual-package floor used for cross-platform solving, not a module-load.

```toml
[system]
cuda = "13.0"
```

## Environment variables `[env]`

Static variables applied when the environment activates. `.env` is also read by default, toggled with `dotenv` in the header.

```toml
[env]
LOG_LEVEL = "info"
CUDA_MODULE_LOADING = "LAZY"
```

## Platform overlays `[on.<platform>]`

Conditionally add deps per platform, and they compile to native pixi targets. Any scope nests under `[on.…]`.

```toml
[on.linux.deps]
cupy = ">=13"

[on.linux-aarch64.pypi.deps]
some-arm-wheel = "*"
```

## Named environments `[envs.<name>]`

Compose extra environments, like pixi features. `no-default = true` excludes the base deps.

```toml
[envs.serving]
no-default = true

[envs.serving.pypi.deps]
vllm = ">=0.6"
```

Install or inspect one with `chefe install serving` or `chefe tree serving`.

## Tasks `[tasks]`

Named commands that run inside the environment, reached with `chefe run <task>`.

```toml
[tasks]
serve = { run = "python -m my_project.server", depends = ["build"] }
build = "python -m my_project.build"
```
