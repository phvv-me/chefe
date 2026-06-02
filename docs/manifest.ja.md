# マニフェスト

すべては一つの `chefe.toml` の中に存在します。ヘッダーは workspace を設定し、`[deps]` と各エコシステムのテーブルがパッケージを宣言し、プラットフォームオーバーレイと名前付き環境がその上に重なります。

## Workspace

```toml
[workspace]
name     = "my-project"
platforms = ["osx-arm64", "linux-64"]
channels = ["conda-forge", "nvidia"]
dotenv   = true                 # read .env into the environment, on by default
```

## 依存関係

素の `[deps]` テーブルは **conda**、デフォルトのソースです。素の文字列はバージョン仕様であり、`*` は任意を意味します。

```toml
[deps]
python = ">=3.11"
nodejs = ">=22"
ripgrep = "*"
pueue  = ">=4"
```

## PyPI

PyPI パッケージは pixi が `uv` を介して **同じ** 環境へ解決します。`[pypi]` は設定を、`[pypi.deps]` はパッケージを、`[pypi.indexes]` は名前付きの追加インデックスを保持します。

```toml
[pypi]
index-strategy = "unsafe-best-match"

[pypi.indexes]
pytorch = "https://download.pytorch.org/whl/cu124"

[pypi.deps]
torch = { version = ">=2.6", index = "pytorch" }
ruff  = ">=0.6"
```

## その他のエコシステム

他のすべてのエコシステムは明示的であり、何も推測されません。

```toml
[cargo.deps]
bookokrat = "*"

[npm.deps]
prettier = ">=3"
"@tobilu/qmd" = "*"
```

!!! tip "ランタイムは自動的に保証されます"
    各エコシステムはインストールと実行のために言語ランタイムを必要とするため、chefe は不足している場合に
    conda-forge から追加します。`[pypi.deps]` は `python` を、`[npm.deps]` は `nodejs` を、
    `[cargo.deps]` は `rust` を、`[gem.deps]` は `ruby` を保証します。`[deps]` に自分でピン留めした
    `python`（や他のもの）を宣言すれば、chefe はそれに手を付けません。これは環境ごとにも当てはまるため、
    `[pypi.deps]` を使う `no-default` 環境でも、自身の `python` を得ます。

## システム要件

クロスプラットフォーム解決に使われる conda の仮想パッケージの下限であり、module-load ではありません。

```toml
[system]
cuda = "13.0"
```

## 環境変数

環境がアクティブ化されるときに適用される静的な変数です。`.env` もデフォルトで読み込まれ、ヘッダーの `dotenv` で切り替えられます。

```toml
[env]
LOG_LEVEL = "info"
CUDA_MODULE_LOADING = "LAZY"
```

## アクティベーションスクリプト

環境がアクティブ化されるときに source されるシェルスクリプトで、静的な環境変数では表現できないセットアップ（計算されたパス、ライブラリのシンボリックリンク）のためのものです。これらは pixi の `[activation] scripts` にコンパイルされます。リポジトリルートからのパスにすれば、生成された `.chefe/` からでも機能し続けます。

```toml
[activation]
scripts = ["scripts/activate.sh"]
```

## プラットフォームオーバーレイ

プラットフォームごとに条件付きで deps を追加でき、それらはネイティブな pixi のターゲットにコンパイルされます。どのスコープも `[on.…]` の下にネストします。

```toml
[on.linux.deps]
cupy = ">=13"

[on.linux-aarch64.pypi.deps]
some-arm-wheel = "*"
```

## 名前付き環境

pixi の feature のように、追加の環境を構成します。`no-default = true` はベースの deps を除外し、`platforms` は環境をビルドできる場所に制限します（そのため GPU 環境はラップトップで解決するときにスキップされます）。

```toml
[envs.serving]
no-default = true
platforms  = ["linux-64", "linux-aarch64"]

[envs.serving.pypi.deps]
vllm = ">=0.6"
```

`chefe install serving` や `chefe tree serving` で、特定の環境をインストールまたは確認できます。

## タスク

環境内で実行される名前付きコマンドで、`chefe run <task>` で到達します。これらは *コード* を実行するのであって、依存関係をインストールすることは決してありません。すべてのパッケージはそのエコシステムの `[<eco>.deps]` に属し、`chefe install` と `chefe global` がそれを管理します。`npm install -g` や `cargo install` を呼び出すタスクは、chefe が置き換えるアンチパターンです。

```toml
[tasks]
serve = { run = "python -m my_project.server", depends = ["build"] }
build = "python -m my_project.build"
```
