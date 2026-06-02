# manifest

一切都存在于一个 `chefe.toml` 中。头部用于配置 workspace，`[deps]` 和各生态系统对应的表用于声明包，平台覆盖（platform overlays）和命名环境（named environments）则在上方进行组合。

## Workspace

```toml
[workspace]
name     = "my-project"
platforms = ["osx-arm64", "linux-64"]
channels = ["conda-forge", "nvidia"]
dotenv   = true                 # 将 .env 读取到环境中，默认开启
```

## 依赖项

基础的 `[deps]` 表是 **conda**，即默认源。纯字符串表示版本规范，`*` 表示任意版本。

```toml
[deps]
python = ">=3.11"
nodejs = ">=22"
ripgrep = "*"
pueue  = ">=4"
```

## PyPI

PyPI 包通过 pixi-via-`uv` 解析到**同一个**环境中。`[pypi]` 包含设置，`[pypi.deps]` 包含包，`[pypi.indexes]` 包含命名的额外索引。

```toml
[pypi]
index-strategy = "unsafe-best-match"

[pypi.indexes]
pytorch = "https://download.pytorch.org/whl/cu124"

[pypi.deps]
torch = { version = ">=2.6", index = "pytorch" }
ruff  = ">=0.6"
```

## 其他生态系统

所有其他生态系统都是显式的，因此不会进行任何推断。

```toml
[cargo.deps]
bookokrat = "*"

[npm.deps]
prettier = ">=3"
"@tobilu/qmd" = "*"
```

!!! tip "运行时会自动确保"
    每个生态系统都需要其语言运行时来安装和运行，因此当缺失时，chefe 会从 conda-forge 添加它。`[pypi.deps]` 确保 `python`，`[npm.deps]` 确保 `nodejs`，`[cargo.deps]` 确保 `rust`，而 `[gem.deps]` 确保 `ruby`。在 `[deps]` 中声明你自己的固定版本 `python`（或其他），chefe 就不会干预。这也适用于每个环境，因此使用 `[pypi.deps]` 的 `no-default` 环境仍然会获得它自己的 `python`。

## 系统要求

这是用于跨平台解析的 conda 虚拟包基准，而非模块加载。

```toml
[system]
cuda = "13.0"
```

## 环境变量

环境激活时应用的静态变量。默认也会读取 `.env`，可通过头部中的 `dotenv` 进行切换。

```toml
[env]
LOG_LEVEL = "info"
CUDA_MODULE_LOADING = "LAZY"
```

## 平台覆盖

按平台有条件地添加依赖项，它们会编译为原生的 pixi 目标。任何作用域都嵌套在 `[on.…]` 下。

```toml
[on.linux.deps]
cupy = ">=13"

[on.linux-aarch64.pypi.deps]
some-arm-wheel = "*"
```

## 命名环境

组合额外的环境，类似于 pixi 特性。`no-default = true` 会排除基础依赖项。

```toml
[envs.serving]
no-default = true

[envs.serving.pypi.deps]
vllm = ">=0.6"
```

使用 `chefe install serving` 或 `chefe tree serving` 安装或检查环境。

## 任务

在环境中运行的命名命令，通过 `chefe run <task>` 调用。

```toml
[tasks]
serve = { run = "python -m my_project.server", depends = ["build"] }
build = "python -m my_project.build"
```