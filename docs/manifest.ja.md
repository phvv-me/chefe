# マニフェスト

すべては一つの `chefe.toml` の中に存在します。ヘッダーは workspace を設定し、`[deps]` と各language/toolchainのテーブルがパッケージを宣言し、プラットフォームオーバーレイと名前付き環境がその上に重なります。

## Workspace

```toml
[workspace]
name     = "my-project"
platforms = ["osx-arm64", "linux-64"]
channels = ["conda-forge", "nvidia"]
dotenv   = true                 # read .env into the environment, on by default
```

## 依存関係

素の `[deps]` テーブルは **conda**、デフォルトの resolver です。素の文字列はバージョン仕様であり、`*` は任意を意味します。

```toml
[deps]
python = ">=3.11"
nodejs = ">=22"
ripgrep = "*"
pueue  = ">=4"
```

## Python

Python パッケージは pixi が **同じ** 環境へ解決します。`[python]` は設定を、`[python.deps]` はパッケージを、`[python.indexes]` は名前付きの追加インデックスを保持します。

```toml
[python]
index-strategy = "unsafe-best-match"

[python.indexes]
pytorch = "https://download.pytorch.org/whl/cu124"

[python.deps]
torch = { version = ">=2.6", index = "pytorch" }
ruff  = ">=0.6"
```

## Runtime キーの toolchain

他のすべてのlanguage/toolchainは明示的であり、何も推測されません。

```toml
[rust.deps]
bookokrat = "*"

[nodejs.dev.deps]
prettier = ">=3"
"@tobilu/qmd" = "*"
```

!!! tip "ランタイムは自動的に保証されます"
    各language/toolchainはインストールと実行のために言語ランタイムを必要とするため、chefe は不足している場合に
    conda-forge から追加します。`[python.deps]` は `python` を保証します。
    `nodejs` や `rust` などの toolchain は `[deps]` に宣言します。`[deps]` に自分でピン留めした
    `python`（や他のもの）を宣言すれば、chefe はそれに手を付けません。これは環境ごとにも当てはまるため、
    `[python.deps]` を使う `no-default` 環境でも、自身の `python` を得ます。

## npm ドライバの選択

Node.js language/toolchainは npm レジストリを使い、`[nodejs]` の中の `manager` がそれをインストールするバイナリを
指定します。コンパイルされる `package.json` はプロジェクトがどれを選んでも同じで、chefe は指定された
ツールを生成された環境ディレクトリ内で実行するため、作業ディレクトリにインストールするパッケージ
マネージャーであれば、chefe が知らないものでも動作します。

```toml
[nodejs]
manager = "pnpm"   # 既定は npm。pnpm、yarn など互換性のある任意のバイナリ

[nodejs.deps]
svelte = ">=5"
```

既定は npm なので、`manager` が未定義なら `[nodejs.deps]` は npm でインストールされます。別のツールを
指定しても変わるのは chefe が実行するバイナリだけで、依存関係もレジストリもファイルも変わりません。

!!! note "ドライバは PATH 上にある必要があります"
    `nodejs` は `[deps]` に宣言します。マネージャー本体は自分で用意します。`manager` が存在しない
    ツールを指している場合、実際のコマンド実行時に失敗します。

## JavaScript アプリケーション

既定では `[nodejs.deps]` は conda 環境の隣、`.chefe/` の中にツールとしてインストールされます。
アプリケーションは `app = true` を設定し、chefe はプロジェクトのルートにインストールして、そこに
完全な `package.json` を書き出します。これにより Vite や SvelteKit などが通常どおり `node_modules`
を解決できます。

```toml
[nodejs]
manager = "pnpm"
app = true

[nodejs.deps]
svelte = ">=5"
vite = ">=8"

[nodejs.package]
type = "module"
pnpm = { onlyBuiltDependencies = ["esbuild", "workerd"] }
```

`[nodejs.package]` はそのまま `package.json` にマージされるため、ツールが期待する任意のフィールドが
手を加えられずに通ります。`type` や `engines` から、pnpm の `onlyBuiltDependencies` のような
パッケージマネージャー独自の設定までです。ファイルは chefe が書き出すので、編集するのは `chefe.toml`
だけで済み、生成された `package.json` は gitignore できるビルド成果物です。

## 開発依存関係

`[dev.*]` はベーススコープを反映し、ビルドやテストには必要だが実行には不要なツールをまとめます。
各グループはそのlanguage/toolchain独自の開発用の仕組みにコンパイルされ、`chefe install` は既定でそれらを
用意します。

```toml
[dev.deps]            # conda の開発ツール
ruff = "*"

[dev.python.deps]       # Python の開発ツール
pytest = ">=8"

[nodejs.dev.deps]     # -> package.json の devDependencies
vite = ">=8"
```

`[nodejs.dev.deps]` は `devDependencies` に入り、`[dev.deps]` と `[dev.python.deps]` は既定の環境に
追加される `dev` フィーチャーになります。そのため、リンターやテストランナーが実行用の依存関係と
並んでインストールされます。これは独自の解決を持つ別環境である `[envs.dev]` よりも軽量です。

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

python = "*"

[on.linux-aarch64.python.deps]
some-arm-wheel = "*"
```

## 名前付き環境

pixi の feature のように、追加の環境を構成します。`no-default = true` はベースの deps を除外し、`platforms` は環境をビルドできる場所に制限します（そのため GPU 環境はラップトップで解決するときにスキップされます）。

```toml

python = "*"

[envs.serving.python.deps]
vllm = ">=0.6"
```

`chefe install serving` や `chefe tree serving` で、特定の環境をインストールまたは確認できます。

## タスク

環境内で実行される名前付きコマンドで、`chefe run <task>` で到達します。これらは *コード* を実行するのであって、依存関係をインストールすることは決してありません。すべてのパッケージはそのlanguage/toolchainの `[<eco>.deps]` に属し、`chefe install` と `chefe global` がそれを管理します。`npm install -g` や `cargo install` を呼び出すタスクは、chefe が置き換えるアンチパターンです。

```toml
[tasks]
serve = { run = "python -m my_project.server", depends = ["build"] }
build = "python -m my_project.build"
```
