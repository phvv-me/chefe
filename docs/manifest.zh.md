# Manifest

一切都存在一份 `chefe.toml` 里。头部配置 workspace，`[deps]` 和各生态专属的表项声明包，平台叠加层和具名环境则在其上层层组合。

## Workspace

```toml
[workspace]
name     = "my-project"
platforms = ["osx-arm64", "linux-64"]
channels = ["conda-forge", "nvidia"]
dotenv   = true                 # read .env into the environment, on by default
```

## 依赖

裸 `[deps]` 表项就是 **conda**，即默认源。裸字符串是一条版本规格说明，`*` 表示任意版本。

```toml
[deps]
python = ">=3.11"
nodejs = ">=22"
ripgrep = "*"
pueue  = ">=4"
```

## PyPI

PyPI 包由 pixi 经 `uv` 解析进**同一个**环境。`[pypi]` 存放设置，`[pypi.deps]` 存放包，`[pypi.indexes]` 存放具名的额外索引。

```toml
[pypi]
index-strategy = "unsafe-best-match"

[pypi.indexes]
pytorch = "https://download.pytorch.org/whl/cu124"

[pypi.deps]
torch = { version = ">=2.6", index = "pytorch" }
ruff  = ">=0.6"
```

## 其他生态

其他每个生态都是显式声明的，不做任何推断。

```toml
[cargo.deps]
bookokrat = "*"

[npm.deps]
prettier = ">=3"
"@tobilu/qmd" = "*"
```

!!! tip "运行时会被自动保证"
    每个生态都需要它的语言运行时才能安装和运行，所以当缺失时 chefe 会从
    conda-forge 把它补上。`[pypi.deps]` 保证 `python`，`[npm.deps]` 保证 `nodejs`，
    `[cargo.deps]` 保证 `rust`，`[gem.deps]` 保证 `ruby`。如果你在 `[deps]` 里自己声明了
    钉死版本的 `python`（或其他），chefe 会原样保留它。这在每个环境里同样成立，
    所以一个使用了 `[pypi.deps]` 的 `no-default` 环境照样会拿到它自己的 `python`。

## 系统要求

用于跨平台求解的 conda 虚拟包下限，而非模块加载（module-load）。

```toml
[system]
cuda = "13.0"
```

## 环境变量

环境激活时应用的静态变量。`.env` 也会被默认读取，可用头部的 `dotenv` 开关切换。

```toml
[env]
LOG_LEVEL = "info"
CUDA_MODULE_LOADING = "LAZY"
```

## 激活脚本

环境激活时被 source 的 shell 脚本，用于静态环境变量无法表达的配置（计算得到的路径、库的符号链接）。它们会编译成 pixi 的 `[activation] scripts`；用仓库根目录的相对路径就能在生成的 `.chefe/` 中继续生效。

```toml
[activation]
scripts = ["scripts/activate.sh"]
```

## 平台叠加层

按平台有条件地添加依赖，它们会编译成原生的 pixi target。任意作用域都可嵌套在 `[on.…]` 之下。

```toml
[on.linux.deps]
cupy = ">=13"

[on.linux-aarch64.pypi.deps]
some-arm-wheel = "*"
```

## 具名环境

像 pixi feature 一样组合出额外的环境。`no-default = true` 会排除基础依赖，`platforms` 把环境限制在它能够构建的平台上（这样在笔记本上求解时会跳过一个 GPU 环境）。

```toml
[envs.serving]
no-default = true
platforms  = ["linux-64", "linux-aarch64"]

[envs.serving.pypi.deps]
vllm = ">=0.6"
```

用 `chefe install serving` 或 `chefe tree serving` 来安装或查看其中之一。

## 任务

在环境内运行的具名命令，通过 `chefe run <task>` 触发。它们运行的是*代码*，绝不安装依赖。每个包都该归在它所属生态的 `[<eco>.deps]` 里，这样 `chefe install` 和 `chefe global` 才能管控它。一个跑去执行 `npm install -g` 或 `cargo install` 的任务，正是 chefe 要取代的反模式。

```toml
[tasks]
serve = { run = "python -m my_project.server", depends = ["build"] }
build = "python -m my_project.build"
```
