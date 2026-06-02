# コマンド

chefe は、統合された manifest 上で pixi の動詞をミラーリングします。ほとんどのコマンドはオプションで `env` を受け取り、デフォルトは `default` です。

| コマンド | 内容 |
|---|---|
| `chefe init` | 現在のディレクトリにスターター用の `chefe.toml` を生成する |
| `chefe sync` | `chefe.toml` を `.chefe/{pixi.toml, package.json, …}` にコンパイルする |
| `chefe install [env]` | 同期を行い、`env` 用のすべてのエコシステムをプロビジョニングする |
| `chefe update [env]` | エコシステム全体で許可された最新バージョンに再解決する |
| `chefe add <pkg…>` | manifest にパッケージを追加し、再同期する |
| `chefe remove <pkg…>` | 宣言されている場所からパッケージを削除し、再同期する |
| `chefe tree [env]` | 宣言済みとインストール済みを比較し、各依存関係を**それぞれの**エコシステムでチェックする |
| `chefe run <task> [args…]` | 環境内でタスクを実行する |
| `chefe x <cmd…>` | uvx や pipx run のように、使い捨て環境でコマンドを実行する |
| `chefe shell [env]` | `env` でアクティブ化されたシェルを開く |
| `chefe global install [name]` | conda の依存関係を共有のグローバル pixi env にインストールする |
| `chefe clean` | 生成された `.chefe/` 環境と manifest を削除する |

## init

```sh
chefe init                 # 現在のディレクトリから名前を取得
chefe init --name myproj
```

現在のプラットフォーム、`conda-forge`、`python >=3.11` を含む最小限の `chefe.toml` を書き込みます。既存の manifest を上書きすることはありません。

## add

Conda がデフォルトのソースであり、フラグを使用して他のエコシステムを選択します。`--spec` はバージョン（デフォルトは `*`）を設定し、`--env` は名前付き環境をターゲットにします。

```sh
chefe add ripgrep numpy
chefe add torch --pypi --spec ">=2.6"
chefe add prettier --npm
chefe add vllm --pypi --env serving
```

編集を行っても、コメントやフォーマットは保持されます。

## tree

```sh
chefe tree
chefe tree serving
```

宣言された各パッケージは、それが宣言されたエコシステムに対してチェックされます。Conda は pixi env に対して、npm は `.chefe/node_modules` に対して、cargo は環境の `.crates.toml` に対してチェックされます。chefe はそれぞれを `✓`（正常）、`≠`（差異あり）、`✗`（欠落）として報告し、推移的なカウントを表示します。

## run and shell

```sh
chefe run build
chefe shell                # デフォルト環境でアクティブ化されたシェル
chefe shell serving
```

## x

```sh
chefe x ruff check .                   # 使い捨て環境でツールを実行、manifest は不要
chefe x --with build python -m build   # --with で追加のパッケージを指定
```

`uvx` や `pipx run` と同様に、`chefe x` はそのツールのための一時的な環境をプロビジョニングして実行し、`chefe.toml` を残しません。

## global install

```sh
chefe global install          # conda [deps] を共有グローバル env として公開
chefe global install mytools
```

## clean

```sh
chefe clean                   # .chefe/ を削除、次回の chefe install で再構築される
```