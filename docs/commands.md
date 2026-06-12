# Commands

chefe mirrors pixi's verbs over the unified manifest. Most commands take an optional `env` that defaults to `default`.

| command | what it does |
|---|---|
| `chefe init` | scaffold a starter `chefe.toml` in the current directory |
| `chefe sync` | compile `chefe.toml` into `.chefe/{pixi.toml, package.json, …}` |
| `chefe install [env]` | sync, then provision every language/toolchain for `env` |
| `chefe activate [env]` | write `.chefe/activate.sh` for this host (HPC modules + pixi env) |
| `chefe update [env]` | re-solve to the newest allowed versions across languages/toolchains |
| `chefe upgrade [pkg…]` | bump the manifest's conda + Python constraints to the latest, then sync |
| `chefe add <pkg…>` | add packages to the manifest, then re-sync |
| `chefe remove <pkg…>` | remove packages wherever they're declared, then re-sync |
| `chefe tree [env]` | declared vs installed, each dep checked in **its own** language/toolchain |
| `chefe run <cmd> [args…]` | run a task or installed executable inside the environment |
| `chefe x <cmd…>` | run a command in a throwaway env, like pipx run |
| `chefe shell [env]` | open an activated shell in `env` |
| `chefe global install [name]` | install every language/toolchain's deps into a shared global env |
| `chefe global add <pkg…>` | add conda packages to the workspace-named global env |
| `chefe global remove <pkg…>` | remove packages from the workspace-named global env |
| `chefe global list` | show all global envs, or one env with `-e` |
| `chefe clean` | remove the generated `.chefe/` env and manifests |

## init

```sh
chefe init                 # name taken from the current directory
chefe init --name myproj
```

Writes a minimal `chefe.toml` with the current platform, `conda-forge`, and `python >=3.11`. It refuses to overwrite an existing manifest.

## add

Conda is the default resolver, and `--language`/`-l` selects Python or any runtime declared in `[deps]`.
`--spec` sets the version (default `*`), while `--env` targets a named environment.

```sh
chefe add ripgrep numpy
chefe add torch -l python --spec ">=2.6"
chefe add prettier -l nodejs
chefe add vllm -l python --env serving
```

Edits keep your comments and formatting.

## tree

```sh
chefe tree
chefe tree serving
```

Each declared package is checked against the language/toolchain it was declared in. Conda goes against the pixi env, Node.js packages against `.chefe/node_modules`, and Rust crates against the env's `.crates.toml`. chefe reports each as `✓` ok, `≠` drift, or `✗` missing, with a transitive count.

## run and shell

```sh
chefe run build
chefe run qmd query "topic" -c zettel
chefe shell                # activated shell in the default env
chefe shell serving
```

`chefe run` first lets pixi resolve declared tasks, then ordinary executables from the managed
environment are available on PATH. That includes Node.js package binaries from `.chefe/node_modules/.bin`,
so a dev tool declared in `[nodejs.dev.deps]` does not need a redundant task just to expose its CLI.

## activate

```sh
chefe activate                # write .chefe/activate.sh for the default env
chefe activate serving
chefe install --activate-only # refresh the script without reinstalling
```

Writes a per-host `.chefe/activate.sh` that loads the manifest's `[modules]` stack and the pixi
environment in one `source`. A job or interactive shell then runs `source .chefe/activate.sh && python -m ...`
with the same modules and env it needs. `chefe install` always regenerates this script, and
`--activate-only` refreshes it against an already provisioned env.

## x

```sh
chefe x ruff check .                   # run a tool in a throwaway env, no manifest needed
chefe x --with build python -m build   # add extra packages with --with
```

Like `pipx run`, `chefe x` provisions an ephemeral environment for the tool and runs it, leaving no `chefe.toml` behind.

## global install

Provision every language/toolchain into one shared global env, the parity of `chefe install` for tools you want everywhere. Conda goes through `pixi global`, and adapters then use binaries from that global env for packages that need a second install step, such as Python, Node.js, and Rust.

```sh
chefe global install          # every language/toolchain's deps into a shared global env
chefe global install mytools  # name the env explicitly
chefe global add ripgrep fd-find
chefe global remove fd-find
chefe global list
chefe global list -e mytools
```

## clean

```sh
chefe clean                   # wipe .chefe/, a fresh chefe install rebuilds it
```
