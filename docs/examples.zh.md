# 示例

一份真实的 `chefe.toml` 是最有说服力的演示。下面是一个多语言 ML monorepo 背后的
manifest，为便于阅读做了精简，但每项特性都一览无余：conda + PyPI（torch 来自自定义索引）
+ npm + cargo、系统 CUDA 下限、环境变量、平台叠加层、隔离的 serving
环境，以及任务。

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

[deps]                                    # bare table is conda, the default source
python      = ">=3.14"
nodejs      = ">=25"
ripgrep-all = ">=0.10"
pandoc      = ">=3.9"
# … runtimes, libs, and CLIs all live here

[pypi]                                    # settings → pixi [pypi-options]
index-strategy   = "unsafe-best-match"
extra-index-urls = ["https://pypi.nvidia.com"]

[pypi.indexes]                            # named indexes a dep can pin
pytorch = "https://download.pytorch.org/whl/cu132"

[pypi.deps]
pydantic = ">=2.13"
polars   = ">=1.40"
torch    = { version = ">=2.11", index = "pytorch" }   # pinned to the named index
# … the rest of the Python stack

[npm.deps]
"@tobilu/qmd" = ">=0.1"
prettier      = ">=3"

[cargo.deps]
bookokrat = { version = ">=0.1", locked = true }

[on.linux.deps]                           # platform overlay → pixi [target.linux]
cuda-nvcc = ">=13.3"
cupy      = ">=14"

[envs.serving]                            # a named, isolated environment
no-default = true

[envs.serving.pypi.deps]
sglang        = ">=0.5"
sglang-kernel = { url = "https://github.com/sgl-project/whl/releases/download/v0.4.2/sglang_kernel-0.4.2+cu130-cp310-abi3-manylinux2014_aarch64.whl" }

[envs.serving.on.linux-64.deps]           # overlay nested inside an env
vllm = { version = ">=0.19", build = "cuda129*" }

[tasks]                                   # run inside the activated env
test = "python -m pytest"
lint = "pre-commit run --all-files"
```

## 上手配置

```sh
chefe sync                 # compile chefe.toml → .chefe/{pixi.toml, package.json}
chefe install              # provision every ecosystem at once (conda, PyPI, npm, cargo)
chefe shell                # an activated shell with all the binaries on PATH
chefe run test             # run a task inside the environment
chefe tree                 # declared vs installed, each checked in its own ecosystem
```

隔离的 `serving` 环境也用同样的方式配置和查看：

```sh
chefe install serving      # solve + provision just the serving env (sglang, vllm, …)
chefe tree serving
```

而对于一次性的工具，则完全不需要 manifest：

```sh
chefe x ruff check .       # run a tool in a throwaway env, like uvx
```
