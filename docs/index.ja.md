# chefe

すべてのパッケージマネージャーを一つのマニフェストで

## インストール

```sh
curl -fsSL https://phvv.me/chefe/install.sh | sh
```

これにより [pixi](https://pixi.sh)（chefe がコンパイル先とするエンジン）と chefe 本体がインストールされます。素のパッケージが欲しい場合は、`pip install chefe` または `uv tool install chefe` を使ってください。

## chefe とは

Conda、PyPI、npm、cargo。実際のプロジェクトではこれらが同時にいくつも必要になり、`pixi.toml`、`package.json`、`Cargo.toml` に散らばってしまいます。chefe はそのヘッドシェフです。**一つの `chefe.toml`** というレシピを書けば、`.chefe/` 配下に各ネイティブマニフェストをコンパイルし、本物のツールを実行し、それらを単一の環境として盛り付けます。ソルバーを自前で再実装することは決してありません。コックたちに働いてもらうのです。

<div class="grid cards" markdown>

- :material-silverware-variant: **一つのレシピ**

    あらゆるエコシステムを単一の `chefe.toml` にまとめます。もう四つのマニフェストを掛け持ちする必要はありません。

- :material-cog-transfer-outline: **ネイティブな出力**

    本物の `pixi.toml`、`package.json` などにコンパイルします。解決は実際のツールが行います。

- :material-source-branch: **組み合わせ可能**

    プラットフォームオーバーレイと名前付き環境が、pixi の feature のように積み重なります。

- :material-broom: **自己完結**

    環境全体が `.chefe/` 内に収まるので、一つのコマンドで一掃できます。

</div>

!!! warning "chefe はまだ初期段階です（`0.0.x`）"
    マニフェスト形式とコマンドは今後も変わる可能性があります。

## クイックスタート

```sh
chefe init                 # scaffold a chefe.toml
chefe add ripgrep          # add deps, use --pypi / --cargo / --npm for others
chefe install              # provision every ecosystem at once
chefe tree                 # what's declared vs installed, per ecosystem
```

## 全体の組み合わせ方

```mermaid
flowchart TB
    subgraph recipe["1 つのレシピ (chefe.toml)"]
        direction LR
        D["[deps]<br/>conda"]
        PY["[pypi.deps]"]
        NP["[npm.deps]"]
        CG["[cargo.deps]"]
    end

    subgraph compiled["chefe sync が .chefe/ を生成"]
        direction LR
        PT["pixi.toml"]
        PJ["package.json"]
    end

    subgraph solve["chefe install が実際のツールを実行"]
        direction LR
        PIXI["pixi<br/>conda-forge"]
        UV["uv<br/>pixi の内部"]
        NPM["npm"]
        CARGO["cargo<br/>pixi run cargo 経由"]
    end

    ENV(["1 つの有効化された環境<br/>PATH 上の .chefe/ プレフィックス"]):::brand

    D --> PT
    PY --> PT
    NP --> PJ
    CG -. ファイルなし、その場でインストール .-> CARGO

    PT --> PIXI
    PIXI --> UV
    PJ --> NPM

    PIXI --> ENV
    UV --> ENV
    NPM --> ENV
    CARGO --> ENV

    classDef brand fill:#eab308,stroke:#1a1a1a,stroke-width:2px,color:#1a1a1a;
```

- **構造** は chefe のスキーマで検証され、**パッケージ仕様** は引き続き各ツールが受け持ちます。
- `chefe add` や `chefe remove` を通じて `chefe.toml` を編集しても、コメントやフォーマットはそのまま保たれます。
- `pixi`（その内部に `uv` を内包）は conda と PyPI を支える中核エンジンであり、他のエコシステムはその上に乗る薄く明示的なレイヤーです。

次は、[マニフェストリファレンス](manifest.md)と[コマンドリファレンス](commands.md)へ。

## 由来

ヘッドシェフがすべての料理を一人で作ることはありません。レシピを書いてライン全体を指揮し、各コックがそれぞれの持ち場で働きます。散らばったパッケージマネージャーはまさにそのラインであり、chefe は一つのレシピからそれらを指揮します。🧑‍🍳
