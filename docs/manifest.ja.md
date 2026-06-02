# manifest

すべてはひとつの `chefe.toml` に集約されます。ヘッダーで workspace を設定し、`[deps]` および各エコシステムごとのテーブルでパッケージを宣言します。また、プラットフォームオーバーレイや名前付き環境を組み合わせて構成します。

## Workspace

```toml
[workspace]
name     = "my-project"
platforms = ["osx-arm64", "linux-64"]
channels = ["conda-forge", "nvidia"]
dotenv   = true                 # .env を環境変数として読み込みます（デフォルトで有効）
```

## Dependencies

単独の `[deps]` テーブルはデフォルトのソースである **conda** を指します。文字列のみの場合はバージョン指定となり、`*` は任意のバージョンを意味します。

```toml
[deps]
python = ">=3.11"
nodejs = ">=22"
ripgrep = "*"
pueue  = ">=4"
```

## PyPI

PyPI パッケージは pixi を介して `uv` により**同一の**環境へ解決されます。`[pypi]` には設定を、`[pypi.deps]` にはパッケージを、`[pypi.indexes]` には名前付きの追加インデックスを記述します。

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

その他のエコシステムはすべて明示的に記述する必要があり、自動的に推論されることはありません。

```toml
[cargo.deps]
bookokrat = "*"

[npm.deps]
prettier = ">=3"
"@tobilu/qmd" = "*"
```

!!! tip "ランタイムは自動的に確保されます"
    各エコシステムはインストールや実行のために言語ランタイムを必要とするため、不足している場合は chefe が conda-forge から追加します。`[pypi.deps]` は `python` を、`[npm.deps]` は `nodejs` を、`[cargo.deps]` は `rust` を、`[gem.deps]` は `ruby` をそれぞれ確保します。`[deps]` で独自の `python`（またはその他）を固定して宣言すれば、chefe はそれに干渉しません。これは環境ごとにも適用されるため、`[pypi.deps]` を使用する `no-default` 環境であっても、独自の `python` が確保されます。

## システム要件

クロスプラットフォーム解決のために使用される conda の仮想パッケージのベースラインであり、モジュールのロードではありません。

```toml
[system]
cuda = "13.0"
```

## 環境変数

環境がアクティブ化されたときに適用される静的な変数です。`.env` もデフォルトで読み込まれますが、ヘッダーの `dotenv` で切り替え可能です。

```toml
[env]
LOG_LEVEL = "info"
CUDA_MODULE_LOADING = "LAZY"
```

## プラットフォームオーバーレイ

プラットフォームごとに条件付きで依存関係を追加します。これらはネイティブの pixi ターゲットにコンパイルされます。任意のスコープを `[on.…]` の下にネストできます。

```toml
[on.linux.deps]
cupy = ">=13"

[on.linux-aarch64.pypi.deps]
some-arm-wheel = "*"
```

## 名前付き環境

pixi の機能のように、追加の環境を構成します。`no-default = true` を指定すると、ベースとなる依存関係を除外します。

```toml
[envs.serving]
no-default = true

[envs.serving.pypi.deps]
vllm = ">=0.6"
```

インストールや確認は `chefe install serving` または `chefe tree serving` で行います。

## Tasks

環境内で実行される名前付きコマンドです。`chefe run <task>` で呼び出します。

```toml
[tasks]
serve = { run = "python -m my_project.server", depends = ["build"] }
build = "python -m my_project.build"
```