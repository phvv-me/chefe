# 示例

一份真实的 `chefe.toml` 是最有说服力的演示。这是多语言 ML monorepo 背后的 manifest，为了可读性进行了精简，但展示了所有功能：conda + PyPI（来自自定义索引的 torch）+ npm + cargo、系统 CUDA 底层、环境变量、平台覆盖、隔离的服务环境以及任务。

```toml
[workspace]
name      = "life"
platforms = ["osx-arm64", "linux-64", "linux-aarch64"]
channels  = ["conda-forge", "nvidia"]
dotenv    = true                          # 自动加载 .env

[system]                                  # conda 虚拟包底层
cuda = "13.0"

[env]                                     # 构建变量；密钥保留在 .env 中
CUDA_DEVICE_ORDER    = "PCI_BUS_ID"
CUDA_VISIBLE_DEVICES = "0"

[deps]                                    # 空表即为 conda，默认源
python      = ">=3.14"
nodejs      = ">=25"
ripgrep-all = ">=0.10"
pandoc      = ">=3.9"
# … 运行时、库和 CLI 都放在这里

[pypi]                                    # 设置 → pixi [pypi-options]
index-strategy   = "unsafe-best-match"
extra-index-urls = ["https://pypi.nvidia.com"]

[pypi.indexes]                            # 依赖项可以锁定的命名索引
pytorch = "https://download.pytorch.org/whl/cu132"

[pypi.deps]
pydantic = ">=2.13"
polars   = ">=1.40"
torch    = { version = ">=2.11", index = "pytorch" }   # 锁定到命名索引
# … 其余的 Python 栈

[npm.deps]
"@tobilu/qmd" = ">=0.1"
prettier      = ">=3"

[cargo.deps]
bookokrat = { version = ">=0.1", locked = true }

[on.linux.deps]                           # 平台覆盖 → pixi [target.linux]
cuda-nvcc = ">=13.3"
cupy      = ">=14"

[envs.serving]                            # 命名隔离环境
no-default = true

[envs.serving.pypi.deps]
sglang        = ">=0.5"
sglang-kernel = { url = "https://github.com/sgl-project/whl/releases/download/v0.4.2/sglang_kernel-0.4.2+cu130-cp310-abi3-manylinux2014_aarch64.whl" }

[envs.serving.on.linux-64.deps]           # 嵌套在环境内的覆盖
vllm = { version = ">=0.19", build = "cuda129*" }

[tasks]                                   # 在激活的环境中运行
test = "python -m pytest"
lint = "pre-commit run --all-files"
```

## 设置

```sh
chefe sync                 # 编译 chefe.toml → .chefe/{pixi.toml, package.json}
chefe install              # 同时配置所有生态系统（conda, PyPI, npm, cargo）
chefe shell                # 激活一个包含所有二进制文件在 PATH 中的 shell
chefe run test             # 在环境中运行任务
chefe tree                 # 查看声明与已安装的对比，每个都在其各自的生态系统中检查
```

隔离的 `serving` 环境的配置和检查方式相同：

```sh
chefe install serving      # 仅解析 + 配置 serving 环境 (sglang, vllm, …)
chefe tree serving
```

对于一次性工具，无需 manifest：

```sh
chefe x ruff check .       # 在临时环境中运行工具，类似于 uvx
```