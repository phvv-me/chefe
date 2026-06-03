# chefe

すべてのパッケージマネージャーを一つのマニフェストで。

Conda、Python、Node.js、Rust、そしてプロジェクトが宣言する toolchain。実際のプロジェクトでは複数を同時に必要とし、それらは `pixi.toml`、`package.json`、言語ごとの manifest に散在します。**chefe** はヘッドシェフです。**一つの `chefe.toml`** レシピを書けば、各ネイティブマニフェストを `.chefe/` 配下にコンパイルし、本物のツールを実行し、単一の環境として盛り付けます。ソルバーを再実装することは決してありません。コックたちを動かすのです。

<div class="grid cards" markdown>

- :material-silverware-variant: **一つのレシピ**

    すべてのlanguage/toolchainを単一の `chefe.toml` に。もう四つのマニフェストをやりくりする必要はありません。

- :material-cog-transfer-outline: **ネイティブな出力**

    本物の `pixi.toml`、`package.json` などにコンパイルします。解決は実際のツールが行います。

- :material-source-branch: **コンポーザブル**

    プラットフォームオーバーレイと名前付き環境は、pixi の feature のように積み重なります。

- :material-broom: **自己完結**

    環境全体が `.chefe/` の中に存在するため、一つのコマンドで消去できます。

</div>

## インストール

```sh
pip install chefe      # or: uv tool install chefe
```

chefe は初回実行時に、コンパイル先のエンジンである [pixi](https://pixi.sh) をインストールします。そのため `pip install` 一回だけで十分です。

```toml title="chefe.toml"
[workspace]
name = "my-project"

[deps]                 # conda, the default resolver
python  = ">=3.12"
nodejs  = ">=25"
ripgrep = "*"

[python.deps]
torch = ">=2.6"

[nodejs.dev.deps]
prettier = ">=3"
```

!!! warning "chefe はまだ初期段階です (`0.0.x`)"
    マニフェストの形式やコマンドはまだ変更される可能性があります。

## 次へ

<div class="grid cards" markdown>

- [:material-cogs: **仕組み**](how-it-works.md) — コンパイルして実行するパイプライン。
- [:material-console: **コマンド**](commands.md) — CLI のすべて。
- [:material-file-document-outline: **マニフェスト**](manifest.md) — `chefe.toml` のすべてのテーブル。
- [:material-test-tube: **サンプル**](examples.md) — 実世界のモノレポのレシピ。

</div>

## 由来

ヘッドシェフはすべての料理を一人で作ることはありません。レシピを書いてラインを統率し、各コックはそれぞれの持ち場で働きます。散在するパッケージマネージャーはまさにそのラインであり、chefe は一つのレシピからそれらを指揮します。🧑‍🍳
