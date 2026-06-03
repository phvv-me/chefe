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

## Choosing the npm driver

The npm ecosystem is the npm registry, and `manager` under `[npm]` names the binary that
installs it. The compiled `package.json` is the same whichever one a project picks, and chefe
runs the named tool inside the generated env, so any package manager that installs into its
working directory works, including ones chefe has never heard of.

```toml
[npm]
manager = "pnpm"   # npm by default; pnpm, bun, aube, yarn, or any other binary

[npm.deps]
svelte = ">=5"
```

npm is the default, so an existing `[npm.deps]` table keeps installing with npm. Naming a
different tool changes only the binary chefe calls, never the deps, the registry, or the file.

!!! note "The driver must be on PATH"
    chefe ensures `nodejs` for the npm ecosystem; the manager binary itself is yours to provide.
    pnpm is on conda-forge, so adding it to `[deps]` keeps an install reproducible, while tools
    like bun or aube ship outside conda and are installed once on the machine.

## JavaScript applications

By default `[npm.deps]` installs as tooling under `.chefe/`, beside the conda env. An application
sets `app = true`, and chefe installs at the project root and writes a full `package.json` there,
so Vite, SvelteKit, and the rest resolve `node_modules` the usual way.

```toml
[npm]
manager = "pnpm"
app = true

[npm.deps]
svelte = ">=5"
vite = ">=8"

[npm.package]
type = "module"
pnpm = { onlyBuiltDependencies = ["esbuild", "workerd"] }
```

`[npm.package]` is merged into `package.json` verbatim, so any field a tool expects rides through,
from `type` and `engines` to a package manager's own settings such as pnpm's
`onlyBuiltDependencies`. chefe writes the file, so `chefe.toml` stays the one thing you edit and a
generated `package.json` is a build artifact you can gitignore.

## Dev dependencies

`[dev.*]` mirrors the base scope for tools you need to build and test but not to run. Each group
compiles to its ecosystem's own dev mechanism, and `chefe install` provisions them by default.

```toml
[dev.deps]            # conda dev tools
ruff = "*"

[dev.pypi.deps]       # pypi dev tools
pytest = ">=8"

[dev.npm.deps]        # -> package.json devDependencies
vite = ">=8"
```

`[dev.npm.deps]` lands in `devDependencies`, while `[dev.deps]` and `[dev.pypi.deps]` become a
`dev` feature added to the default environment, so your linters and test runner install beside the
runtime deps. This is lighter than a full `[envs.dev]`, which is a separate environment with its
own solve.

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

Named commands that run inside the environment, reached with `chefe run <task>`. They run *code*, never install dependencies. Every package belongs in its ecosystem's `[<eco>.deps]` so `chefe install` and `chefe global` own it. A task that shells out to `npm install -g` or `cargo install` is the anti-pattern chefe replaces.

```toml
[tasks]
serve = { run = "python -m my_project.server", depends = ["build"] }
build = "python -m my_project.build"
```
