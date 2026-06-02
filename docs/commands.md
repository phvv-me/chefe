# Commands

chefe mirrors pixi's verbs over the unified manifest. Most commands take an optional `env` that defaults to `default`.

| command | what it does |
|---|---|
| `chefe init` | scaffold a starter `chefe.toml` in the current directory |
| `chefe sync` | compile `chefe.toml` into `.chefe/{pixi.toml, package.json, …}` |
| `chefe install [env]` | sync, then provision every ecosystem for `env` |
| `chefe update [env]` | re-solve to the newest allowed versions across ecosystems |
| `chefe add <pkg…>` | add packages to the manifest, then re-sync |
| `chefe remove <pkg…>` | remove packages wherever they're declared, then re-sync |
| `chefe tree [env]` | declared vs installed, each dep checked in **its own** ecosystem |
| `chefe run <task> [args…]` | run a task inside the environment |
| `chefe shell [env]` | open an activated shell in `env` |
| `chefe global install [name]` | install the conda deps into the shared global pixi env |
| `chefe clean` | remove the generated `.chefe/` env and manifests |

## init

```sh
chefe init                 # name taken from the current directory
chefe init --name myproj
```

Writes a minimal `chefe.toml` with the current platform, `conda-forge`, and `python >=3.11`. It refuses to overwrite an existing manifest.

## add

Conda is the default source, and flags pick another ecosystem. `--spec` sets the version (default `*`), while `--env` targets a named environment.

```sh
chefe add ripgrep numpy
chefe add torch --pypi --spec ">=2.6"
chefe add prettier --npm
chefe add vllm --pypi --env serving
```

Edits keep your comments and formatting.

## tree

```sh
chefe tree
chefe tree serving
```

Each declared package is checked against the ecosystem it was declared in. Conda goes against the pixi env, npm against `.chefe/node_modules`, and cargo against the env's `.crates.toml`. chefe reports each as `✓` ok, `≠` drift, or `✗` missing, with a transitive count.

## run and shell

```sh
chefe run build
chefe shell                # activated shell in the default env
chefe shell serving
```

## global install

```sh
chefe global install          # exposes the conda [deps] as a shared global env
chefe global install mytools
```

## clean

```sh
chefe clean                   # wipe .chefe/, a fresh chefe install rebuilds it
```
