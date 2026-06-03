# 例

実際の `chefe.toml` こそが、最も説得力のある手引きになります。これは多言語 ML モノレポの
背後にあるマニフェストで、読みやすさのために簡略化していますが、あらゆる機能を
盛り込んでいます。conda + Python（カスタムインデックスからの torch）+ Node.js + Rust、システムの CUDA
下限、環境変数、プラットフォームオーバーレイ、隔離された serving
環境、そしてタスクです。

```toml
[workspace]
name      = "life"
platforms = ["osx-arm64", "linux-64", "linux-aarch64"]
channels  = ["conda-forge", "nvidia"]
dotenv    = true                          # auto-load .env

[system]                                  # the conda virtual-package floor
cuda = "13.0"

[env]                                     # build vars; secrets stay in .env
CUDA_DEVICE_ORDER    = "PCI_BUS_ID"
CUDA_VISIBLE_DEVICES = "0"

[deps]                                    # bare table is conda, the default resolver
python      = ">=3.14"
nodejs      = ">=25"
rust        = "*"
ripgrep-all = ">=0.10"
pandoc      = ">=3.9"
# … runtimes, libs, and CLIs all live here

[python]                                    # settings for Python packages
index-strategy   = "unsafe-best-match"
extra-index-urls = ["https://pypi.nvidia.com"]

[python.indexes]                            # named indexes a dep can pin
pytorch = "https://download.pytorch.org/whl/cu132"

[python.deps]
pydantic = ">=2.13"
polars   = ">=1.40"
torch    = { version = ">=2.11", index = "pytorch" }   # pinned to the named index
# … the rest of the Python stack

[nodejs.dev.deps]
"@tobilu/qmd" = ">=0.1"
prettier      = ">=3"

[rust.deps]
bookokrat = { version = ">=0.1", locked = true }

[on.linux.deps]                           # platform overlay → pixi [target.linux]
cuda-nvcc = ">=13.3"
cupy      = ">=14"

[envs.serving]                            # a named, isolated environment
no-default = true

[envs.serving.deps]
python = "*"

[envs.serving.python.deps]
sglang        = ">=0.5"
sglang-kernel = { url = "https://github.com/sgl-project/whl/releases/download/v0.4.2/sglang_kernel-0.4.2+cu130-cp310-abi3-manylinux2014_aarch64.whl" }

[envs.serving.on.linux-64.deps]           # overlay nested inside an env
vllm = { version = ">=0.19", build = "cuda129*" }

[tasks]                                   # run inside the activated env
test = "python -m pytest"
lint = "pre-commit run --all-files"
```

## セットアップ

```sh
chefe sync                 # compile chefe.toml → .chefe/{pixi.toml, package.json}
chefe install              # provision every language/toolchain at once
chefe shell                # an activated shell with all the binaries on PATH
chefe run test             # run a task inside the environment
chefe tree                 # declared vs installed, each checked in its own language/toolchain
```

隔離された `serving` 環境も、同じ方法でプロビジョニングおよび検査できます。

```sh
chefe install serving      # solve + provision just the serving env (sglang, vllm, …)
chefe tree serving
```

マニフェストを必要としない単発のツール実行には、次のようにします。

```sh
chefe x ruff check .       # run a tool in a throwaway env, like uvx
```
