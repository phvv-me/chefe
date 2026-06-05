# コマンド

chefe は統一マニフェストに対して pixi の動詞を反映します。ほとんどのコマンドはオプションの `env` を取り、デフォルトは `default` です。

| コマンド | 動作 |
|---|---|
| `chefe init` | カレントディレクトリに出発点となる `chefe.toml` を生成する |
| `chefe sync` | `chefe.toml` を `.chefe/{pixi.toml, package.json, …}` へコンパイルする |
| `chefe install [env]` | sync してから、`env` のすべてのlanguage/toolchainをプロビジョニングする |
| `chefe update [env]` | language/toolchain全体で許可された最新バージョンへ再解決する |
| `chefe upgrade [pkg…]` | マニフェストの conda + Python の制約を最新に引き上げてから sync する |
| `chefe add <pkg…>` | マニフェストにパッケージを追加してから再 sync する |
| `chefe remove <pkg…>` | 宣言されている場所からパッケージを削除してから再 sync する |
| `chefe tree [env]` | 宣言済みとインストール済みを、各 dep を **それ自身の** language/toolchainで照合する |
| `chefe run <task> [args…]` | 環境内でタスクを実行する |
| `chefe x <cmd…>` | pipx run のように、使い捨ての環境でコマンドを実行する |
| `chefe shell [env]` | `env` でアクティブ化されたシェルを開く |
| `chefe global install [name]` | すべてのlanguage/toolchainの deps を共有のグローバル環境へインストールする |
| `chefe clean` | 生成された `.chefe/` 環境とマニフェストを削除する |

## init

```sh
chefe init                 # name taken from the current directory
chefe init --name myproj
```

現在のプラットフォーム、`conda-forge`、`python >=3.11` を備えた最小限の `chefe.toml` を書き込みます。既存のマニフェストを上書きすることは拒否します。

## add

Conda がデフォルトの resolver であり、`--language`/`-l` で Python または `[deps]` に宣言された任意の runtime を選びます。`--spec` はバージョンを設定し（デフォルトは `*`）、`--env` は名前付き環境を対象にします。

```sh
chefe add ripgrep numpy
chefe add torch -l python --spec ">=2.6"
chefe add prettier -l nodejs
chefe add vllm -l python --env serving
```

編集してもコメントと書式は保たれます。

## tree

```sh
chefe tree
chefe tree serving
```

宣言された各パッケージは、それが宣言されたソースに対して照合されます。Conda は pixi 環境に対して、Node.js パッケージは `.chefe/node_modules` に対して、Rust crate は環境の `.crates.toml` に対して照合されます。chefe はそれぞれを `✓` ok、`≠` ドリフト、`✗` 欠落として、推移的な数とともに報告します。

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

`pipx run` のように、`chefe x` はツールのために一時的な環境をプロビジョニングして実行し、`chefe.toml` を残しません。

## global install

すべてのソースを一つの共有グローバル環境へプロビジョニングします。これはどこでも使いたいツールのための `chefe install` の対応物です。Conda は `pixi global` を経由します。その後、Python、Node.js、Rust のように二段階目が必要なソースでは、アダプターがそのグローバル環境のバイナリを使います。

```sh
chefe global install          # every language/toolchain's deps into a shared global env
chefe global install mytools  # name the env explicitly
```

## clean

```sh
chefe clean                   # wipe .chefe/, a fresh chefe install rebuilds it
```
