# コマンド

chefe は pixi のコマンド体系を、統合されたマニフェストの上にそのまま再現します。ほとんどのコマンドは省略可能な `env` を受け取り、デフォルトは `default` です。

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
| `chefe x <cmd…>` | run a command in a throwaway env, like uvx or pipx run |
| `chefe shell [env]` | open an activated shell in `env` |
| `chefe global install [name]` | install the conda deps into the shared global pixi env |
| `chefe clean` | remove the generated `.chefe/` env and manifests |

## init

```sh
chefe init                 # name taken from the current directory
chefe init --name myproj
```

現在のプラットフォーム、`conda-forge`、`python >=3.11` を含む最小限の `chefe.toml` を書き出します。既存のマニフェストがある場合は上書きを拒否します。

## add

conda がデフォルトのソースで、フラグを付けると別のエコシステムを選べます。`--spec` はバージョンを指定し（デフォルトは `*`）、`--env` は名前付き環境を対象にします。

```sh
chefe add ripgrep numpy
chefe add torch --pypi --spec ">=2.6"
chefe add prettier --npm
chefe add vllm --pypi --env serving
```

編集してもコメントやフォーマットはそのまま保たれます。

## tree

```sh
chefe tree
chefe tree serving
```

宣言された各パッケージは、それが宣言されたエコシステムに照らして検査されます。conda は pixi 環境に対して、npm は `.chefe/node_modules` に対して、cargo は環境の `.crates.toml` に対して照合されます。chefe はそれぞれを `✓`（正常）、`≠`（ずれ）、`✗`（欠落）として報告し、推移的依存の数も併せて示します。

## run と shell

```sh
chefe run build
chefe shell                # activated shell in the default env
chefe shell serving
```

## x

```sh
chefe x ruff check .                   # run a tool in a throwaway env, no manifest needed
chefe x --with build python -m build   # add extra packages with --with
```

`uvx` や `pipx run` と同様に、`chefe x` はそのツールのために一時的な環境を用意して実行し、`chefe.toml` を後に残しません。

## global install

```sh
chefe global install          # exposes the conda [deps] as a shared global env
chefe global install mytools
```

## clean

```sh
chefe clean                   # wipe .chefe/, a fresh chefe install rebuilds it
```
