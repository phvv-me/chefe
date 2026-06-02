# マニフェスト

すべては一つの `chefe.toml` に収まります。ヘッダーが workspace を設定し、`[deps]` とエコシステムごとのテーブルがパッケージを宣言し、プラットフォームオーバーレイと名前付き環境がその上に重なって構成されます。

## Workspace

```toml
[workspace]
name     = "my-project"
platforms = ["osx-arm64", "linux-64"]
channels = ["conda-forge", "nvidia"]
dotenv   = true                 # read .env into the environment, on by default
```

## 依存関係

素の `[deps]` テーブルは **conda** で、デフォルトのソースです。素の文字列はバージョン仕様であり、`*` は任意を意味します。

```toml
[deps]
python = ">=3.11"
nodejs = ">=22"
ripgrep = "*"
pueue  = ">=4"
```

## PyPI

PyPI パッケージは、pixi が `uv` を介して **同じ** 環境内へ解決します。`[pypi]` には設定を、`[pypi.deps]` にはパッケージを、`[pypi.indexes]` には名前付きの追加インデックスを記述します。

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

!!! tip "ランタイムは自動的に確保されます"
    各エコシステムはインストールと実行に言語ランタイムを必要とするため、chefe は欠けている場合に
    conda-forge から追加します。`[pypi.deps]` は `python` を、`[npm.deps]` は `nodejs` を、
    `[cargo.deps]` は `rust` を、`[gem.deps]` は `ruby` を確保します。`[deps]` に自分でピン留めした
    `python`（やその他）を宣言すれば、chefe はそれをそのままにします。これは環境ごとにも当てはまるので、
    `[pypi.deps]` を使う `no-default` 環境も独自の `python` を得ます。

## システム要件

クロスプラットフォーム解決に使われる conda 仮想パッケージの下限であり、モジュールロードではありません。

```toml
[system]
cuda = "13.0"
```

## 環境変数

環境がアクティブになるときに適用される静的な変数です。`.env` もデフォルトで読み込まれ、ヘッダーの `dotenv` で切り替えられます。

```toml
[env]
LOG_LEVEL = "info"
CUDA_MODULE_LOADING = "LAZY"
```

## プラットフォームオーバーレイ

プラットフォームごとに条件付きで依存関係を追加でき、これはネイティブな pixi ターゲットへコンパイルされます。どのスコープでも `[on.…]` の下にネストできます。

```toml
[on.linux.deps]
cupy = ">=13"

[on.linux-aarch64.pypi.deps]
some-arm-wheel = "*"
```

## 名前付き環境

pixi の feature のように、追加の環境を組み合わせて構成します。`no-default = true` はベースの依存関係を除外します。

```toml
[envs.serving]
no-default = true

[envs.serving.pypi.deps]
vllm = ">=0.6"
```

`chefe install serving` または `chefe tree serving` で、いずれかをインストールまたは検査できます。

## タスク

環境内で実行される名前付きコマンドで、`chefe run <task>` で呼び出します。

```toml
[tasks]
serve = { run = "python -m my_project.server", depends = ["build"] }
build = "python -m my_project.build"
```
