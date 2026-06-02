# manifest

一切都放在一份 `chefe.toml` 中。头部配置 workspace，`[deps]` 和各个按生态系统划分的表用来声明包，平台叠加层与具名环境则在其上组合。

## Workspace

```toml
[workspace]
name     = "my-project"
platforms = ["osx-arm64", "linux-64"]
channels = ["conda-forge", "nvidia"]
dotenv   = true                 # read .env into the environment, on by default
```

## 依赖

不带前缀的 `[deps]` 表就是 **conda**，即默认源。直接写一个字符串表示版本规格，`*` 表示任意版本。

```toml
[deps]
python = ">=3.11"
nodejs = ">=22"
ripgrep = "*"
pueue  = ">=4"
```

## PyPI

PyPI 包由 pixi 通过 `uv` 求解，并装入**同一个**环境。`[pypi]` 存放设置，`[pypi.deps]` 存放包，`[pypi.indexes]` 存放具名的额外索引。

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

其他每个生态系统都是显式的，不会有任何推断。

```toml
[cargo.deps]
bookokrat = "*"

[npm.deps]
prettier = ">=3"
"@tobilu/qmd" = "*"
```

!!! tip "运行时会自动补齐"
    每个生态系统都需要相应的语言运行时才能安装和运行，因此 chefe 会在运行时缺失时从
    conda-forge 自动补上。`[pypi.deps]` 会确保有 `python`，`[npm.deps]` 确保有 `nodejs`，
    `[cargo.deps]` 确保有 `rust`，`[gem.deps]` 确保有 `ruby`。只要你在 `[deps]` 中声明了自己锁定版本的
    `python`（或其他运行时），chefe 就不会去动它。这一规则对每个环境同样成立，
    因此一个使用 `[pypi.deps]` 的 `no-default` 环境仍会拥有自己的 `python`。

## 系统需求

用于跨平台求解的 conda 虚拟包下限，而非运行时的模块加载。

```toml
[system]
cuda = "13.0"
```

## 环境变量

环境激活时设置的静态变量。`.env` 默认也会被读取，可通过头部的 `dotenv` 开关来控制。

```toml
[env]
LOG_LEVEL = "info"
CUDA_MODULE_LOADING = "LAZY"
```

## 平台叠加层

按平台有条件地添加依赖，它们会编译成原生的 pixi target。任何作用域都可以嵌套在 `[on.…]` 之下。

```toml
[on.linux.deps]
cupy = ">=13"

[on.linux-aarch64.pypi.deps]
some-arm-wheel = "*"
```

## 具名环境

像 pixi 的 feature 一样组合额外的环境。`no-default = true` 会排除基础依赖。

```toml
[envs.serving]
no-default = true

[envs.serving.pypi.deps]
vllm = ">=0.6"
```

用 `chefe install serving` 或 `chefe tree serving` 就能安装或查看其中某个环境。

## 任务

在环境内运行的具名命令，通过 `chefe run <task>` 调用。

```toml
[tasks]
serve = { run = "python -m my_project.server", depends = ["build"] }
build = "python -m my_project.build"
```
