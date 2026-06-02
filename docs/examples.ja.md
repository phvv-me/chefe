# 例

実際の `chefe.toml` を見ることが、最も説得力のあるツアーになります。これは、マルチ言語の ML monorepo の背後にある manifest です。読みやすさのために簡略化されていますが、すべての機能が網羅されています。conda + PyPI (カスタムインデックスからの torch) + npm + cargo、システム CUDA の基盤、環境変数、プラットフォームオーバーレイ、分離された serving 環境、そしてタスクが含まれています。

```toml
[workspace]
name      = "life"
platforms = ["osx-arm64", "linux-64", "linux-aarch64"]
channels  = ["conda-forge", "nvidia"]
dotenv    = true                          # .env を自動読み込み

[system]                                  # conda の仮想パッケージ基盤
cuda = "13.0"

[env]                                     # ビルド変数。シークレットは .env に保持
CUDA_DEVICE_ORDER    = "PCI_BUS_ID"
CUDA_VISIBLE_DEVICES = "0"

[deps]                                    # テーブル単体は conda（デフォルトのソース）
python      = ">=3.14"
nodejs      = ">=25"
ripgrep-all = ">=0.10"
pandoc      = ">=3.9"
# … ランタイム、ライブラリ、CLI はすべてここに配置

[pypi]                                    # 設定 → pixi [pypi-options]
index-strategy   = "unsafe-best-match"
extra-index-urls = ["https://pypi.nvidia.com"]

[pypi.indexes]                            # 依存関係が指定可能な名前付きインデックス
pytorch = "https://download.pytorch.org/whl/cu132"

[pypi.deps]
pydantic = ">=2.13"
polars   = ">=1.40"
torch    = { version = ">=2.11", index = "pytorch" }   # 名前付きインデックスに固定
# … Python スタックの残り

[npm.deps]
"@tobilu/qmd" = ">=0.1"
prettier      = ">=3"

[cargo.deps]
bookokrat = { version = ">=0.1", locked = true }

[on.linux.deps]                           # プラットフォームオーバーレイ → pixi [target.linux]
cuda-nvcc = ">=13.3"
cupy      = ">=14"

[envs.serving]                            # 名前付きの分離された環境
no-default = true

[envs.serving.pypi.deps]
sglang        = ">=0.5"
sglang-kernel = { url = "https://github.com/sgl-project/whl/releases/download/v0.4.2/sglang_kernel-0.4.2+cu130-cp310-abi3-manylinux2014_aarch64.whl" }

[envs.serving.on.linux-64.deps]           # 環境内にネストされたオーバーレイ
vllm = { version = ">=0.19", build = "cuda129*" }

[tasks]                                   # アクティブ化された環境内で実行
test = "python -m pytest"
lint = "pre-commit run --all-files"
```

## セットアップ

```sh
chefe sync                 # chefe.toml を .chefe/{pixi.toml, package.json} にコンパイル
chefe install              # すべてのエコシステムを一度にプロビジョニング (conda, PyPI, npm, cargo)
chefe shell                # すべてのバイナリが PATH にあるアクティブ化されたシェル
chefe run test             # 環境内でタスクを実行
chefe tree                 # 宣言済みとインストール済みの比較、それぞれのエコシステムでチェック
```

分離された `serving` 環境も同様の方法でプロビジョニングおよび検査されます：

```sh
chefe install serving      # serving 環境のみを解決 + プロビジョニング (sglang, vllm, …)
chefe tree serving
```

また、単発のツールであれば manifest は不要です：

```sh
chefe x ruff check .       # uvx のように、使い捨て環境でツールを実行
```