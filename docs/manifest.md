# The manifest

Everything lives in one `chefe.toml`. The header configures the workspace, `[deps]` declares conda packages and runtime packages, matching runtime tables declare toolchain packages, and platform overlays and named environments compose on top.

## Workspace

```toml
[workspace]
name     = "my-project"
platforms = ["osx-arm64", "linux-64"]
channels = ["conda-forge", "nvidia"]
dotenv   = true                 # read .env into the environment, on by default
```

## Dependencies

The bare `[deps]` table is **conda**, the default resolver. A bare string is a version spec, and `*` means any.

```toml
[deps]
python = ">=3.11"
nodejs = ">=22"
ripgrep = "*"
pueue  = ">=4"
```

## Python

Python packages are resolved into the **same** environment. `[python]` holds settings, `[python.deps]` the packages, and `[python.indexes]` named extra indexes.

```toml
[python]
index-strategy = "unsafe-best-match"

[python.indexes]
pytorch = "https://download.pytorch.org/whl/cu124"

[python.deps]
torch = { version = ">=2.6", index = "pytorch" }
ruff  = ">=0.6"
```

## Runtime-keyed toolchains

Any package declared in `[deps]` can have a matching table with toolchain settings and packages.
The table name is the contract. Chefe does not need a language catalog.

```toml
[deps]
nodejs = ">=25"
rust = "*"
zig = ">=0.14"
cxx-compiler = "*"

[nodejs]
manager = "pnpm"

[nodejs.dev.deps]
"@tobilu/qmd" = "*"
prettier = ">=3"

[rust.deps]
bookokrat = "*"

[zig]
manager = "zig"

[cxx-compiler]
manager = "conan"

[cxx-compiler.deps]
fmt = ">=11"
```

`[nodejs]` has an adapter that emits `package.json` and runs `manager`, defaulting to `npm`.
`[rust]` has an adapter that installs crates with Cargo. Other toolchains are still discovered,
validated, shown in `chefe tree`, and can expose extra executable directories through `bin_dirs`.

!!! tip "Let tools fail where they run"
    Chefe does not preflight every possible manager. If `manager = "zig"` or `manager = "conan"`
    names a binary that is unavailable, the real command fails when it is used.

A runtime table only works when its name is also declared in `[deps]`. A table with no matching package fails with a self-contained error that names the running chefe and leads with the upgrade path, since the usual cause is a table from a newer chefe than the one installed. Run `pip install -U chefe`, or add the name to `[deps]`, or remove the table.

## JavaScript applications

By default `[nodejs.deps]` installs as tooling under `.chefe/`, beside the conda env. An application
sets `app = true`, and chefe installs at the project root and writes a full `package.json` there,
so Vite, SvelteKit, and the rest resolve `node_modules` the usual way.

```toml
[deps]
nodejs = ">=25"

[nodejs]
manager = "pnpm"
app = true

[nodejs.deps]
svelte = ">=5"
vite = ">=8"

[nodejs.package]
type = "module"
pnpm = { onlyBuiltDependencies = ["esbuild", "workerd"] }
```

`[nodejs.package]` is merged into `package.json` verbatim, so any field a tool expects rides through,
from `type` and `engines` to a package manager's own settings such as pnpm's
`onlyBuiltDependencies`. chefe writes the file, so `chefe.toml` stays the one thing you edit and a
generated `package.json` is a build artifact you can gitignore.

## Dev dependencies

`[dev.*]` mirrors the base scope for tools you need to build and test but not to run. Each group
compiles to its language/toolchain's own dev mechanism, and `chefe install` provisions them by default.

```toml
[dev.deps]            # conda dev tools
ruff = "*"

[dev.python.deps]       # Python dev tools
pytest = ">=8"

[nodejs.dev.deps]     # -> package.json devDependencies
vite = ">=8"
```

`[nodejs.dev.deps]` lands in `devDependencies`, while `[dev.deps]` and `[dev.python.deps]` become a
`dev` feature added to the default environment, so your linters and test runner install beside the
runtime deps. This is lighter than a full `[envs.dev]`, which is a separate environment with its
own solve.

Command-line tools declared in `[nodejs.dev.deps]` are available through `chefe run` and `chefe shell`.
For example, declaring `@tobilu/qmd` here lets `chefe run qmd ...` find the executable linked
under `.chefe/node_modules/.bin`. Do not add a task that only repeats that binary path.

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

Shell scripts sourced when the environment activates, for setup that static env vars can't express (computed paths, library symlinks). They compile to pixi's `[activation] scripts`, and a repo-root path keeps working from the generated `.chefe/`.

```toml
[activation]
scripts = ["scripts/activate.sh"]
```

## HPC modules

`[modules]` is a stack of HPC environment modules as `name = "version"` pairs. Each pair becomes one `module load name/version` line, in declared order, baked into the generated `.chefe/activate.sh`. So `source .chefe/activate.sh` loads the same modules a job needs before it runs.

```toml
[modules]
cuda = "13.2"
gcc  = "15.2.0"
```

This compiles to `module purge` followed by `module load cuda/13.2 gcc/15.2.0`. On a host without Lmod or environment-modules (a laptop, for instance) the load is guarded by `command -v module` and becomes a harmless no-op, so the same manifest is safe everywhere. Refresh the script for the current host with `chefe install` or `chefe activate`.

## Platform overlays

Conditionally add deps per platform, and they compile to native pixi targets. Any scope nests under `[on.…]`.

```toml
[on.linux.deps]
cupy = ">=13"

[on.linux-aarch64.deps]
python = "*"

[on.linux-aarch64.python.deps]
some-arm-wheel = "*"
```

## Named environments

Compose extra environments, like pixi features. `no-default = true` excludes the base deps, and `platforms` restricts the environment to where it can build (so a GPU env is skipped when solving on a laptop).

```toml
[envs.serving]
no-default = true
platforms  = ["linux-64", "linux-aarch64"]

[envs.serving.deps]
python = "*"

[envs.serving.python.deps]
vllm = ">=0.6"
```

Install or inspect one with `chefe install serving` or `chefe tree serving`.

## Tasks

Named commands that run inside the environment, reached with `chefe run <task>`. They run *code*, never install dependencies. Every package belongs in `[deps]`, `[python.deps]`, or a runtime-keyed table such as `[nodejs.deps]` or `[rust.deps]`, so `chefe install` and `chefe global` own it. Add packages with `chefe add pkg -l python`, `chefe add pkg -l nodejs`, or another declared language/toolchain. A task that shells out to `npm install -g` or `cargo install` is the anti-pattern chefe replaces.

```toml
[tasks]
serve = { run = "python -m my_project.server", depends = ["build"] }
build = "python -m my_project.build"
```
