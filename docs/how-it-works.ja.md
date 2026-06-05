# 仕組み

`chefe sync` は一つの `chefe.toml` を `.chefe/` 配下のネイティブマニフェストへコンパイルし、続いて `chefe install` がそれぞれを本物のツールに渡して、解決と単一の共有環境のビルドを行わせます。

```mermaid
flowchart TB
    subgraph recipe["一つのレシピ (chefe.toml)"]
        direction LR
        D["[deps]<br/>conda"]
        PY["[python.deps]"]
        NP["[nodejs.deps]"]
        CG["[rust.deps]"]
    end

    subgraph compiled["chefe sync が .chefe/ を生成"]
        direction LR
        PT["pixi.toml"]
        PJ["package.json"]
    end

    subgraph solve["chefe install が本物のツールを実行"]
        direction LR
        PIXI["pixi<br/>conda-forge + Python"]
        NPM["npm"]
        CARGO["cargo<br/>via pixi run cargo"]
    end

    ENV(["一つのアクティブ化された環境<br/>PATH 上の .chefe/ プレフィックス"]):::brand

    D --> PT
    PY --> PT
    NP --> PJ
    CG -. ファイルなし、その場でインストール .-> CARGO

    PT --> PIXI
    PJ --> NPM

    PIXI --> ENV
    NPM --> ENV
    CARGO --> ENV

    classDef brand fill:#eab308,stroke:#1a1a1a,stroke-width:2px,color:#1a1a1a;
```

- **構造** は chefe のスキーマによって検証され、**パッケージ仕様** は各ツールの仕事のままです。
- `chefe add` と `chefe remove` を通じて `chefe.toml` を編集すると、コメントと書式が保たれます。
- `pixi` は conda と Python packages のための深いエンジンであり、他のlanguage/toolchainはその上に重なる薄く明示的なレイヤーです。

## クイックスタート

```sh
chefe init                 # scaffold a chefe.toml
chefe add ripgrep          # conda is the default resolver
chefe add torch -l python
chefe add prettier -l nodejs
chefe install              # provision every language/toolchain at once
chefe tree                 # what's declared vs installed, per language/toolchain
```

次は [マニフェストリファレンス](manifest.md) と [コマンドリファレンス](commands.md) です。
