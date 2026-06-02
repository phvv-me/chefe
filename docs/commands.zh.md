# 命令

chefe 在统一的 manifest 之上镜像了 pixi 的动词。大多数命令都接受一个可选的 `env`，默认为 `default`。

| 命令 | 功能 |
|---|---|
| `chefe init` | 在当前目录中构建一个初始的 `chefe.toml` |
| `chefe sync` | 将 `chefe.toml` 编译为 `.chefe/{pixi.toml, package.json, …}` |
| `chefe install [env]` | 同步，然后为 `env` 配置所有生态系统 |
| `chefe update [env]` | 重新解析各生态系统中允许的最新版本 |
| `chefe add <pkg…>` | 将包添加到 manifest，然后重新同步 |
| `chefe remove <pkg…>` | 从声明位置移除包，然后重新同步 |
| `chefe tree [env]` | 检查声明与已安装的依赖，每个依赖都在**其各自的**生态系统中进行检查 |
| `chefe run <task> [args…]` | 在环境中运行任务 |
| `chefe x <cmd…>` | 在临时环境中运行命令，类似于 uvx 或 pipx run |
| `chefe shell [env]` | 在 `env` 中打开一个已激活的 shell |
| `chefe global install [name]` | 将 conda 依赖安装到共享的全局 pixi 环境中 |
| `chefe clean` | 移除生成的 `.chefe/` 环境和 manifest |

## init

```sh
chefe init                 # 名称取自当前目录
chefe init --name myproj
```

写入一个包含当前平台、`conda-forge` 和 `python >=3.11` 的最小化 `chefe.toml`。它拒绝覆盖现有的 manifest。

## add

Conda 是默认源，标志位可选择其他生态系统。`--spec` 用于设置版本（默认为 `*`），而 `--env` 用于指定目标环境。

```sh
chefe add ripgrep numpy
chefe add torch --pypi --spec ">=2.6"
chefe add prettier --npm
chefe add vllm --pypi --env serving
```

编辑操作会保留您的注释和格式。

## tree

```sh
chefe tree
chefe tree serving
```

每个声明的包都会根据其声明所在的生态系统进行检查。Conda 针对 pixi 环境，npm 针对 `.chefe/node_modules`，cargo 针对环境的 `.crates.toml`。chefe 会报告每个包的状态：`✓` 表示正常，`≠` 表示偏差，`✗` 表示缺失，并附带传递依赖计数。

## run 和 shell

```sh
chefe run build
chefe shell                # 在默认环境中激活 shell
chefe shell serving
```

## x

```sh
chefe x ruff check .                   # 在临时环境中运行工具，无需 manifest
chefe x --with build python -m build   # 使用 --with 添加额外包
```

类似于 `uvx` 或 `pipx run`，`chefe x` 为该工具配置一个临时环境并运行它，不会留下任何 `chefe.toml`。

## global install

```sh
chefe global install          # 将 conda [deps] 暴露为共享的全局环境
chefe global install mytools
```

## clean

```sh
chefe clean                   # 清除 .chefe/，全新的 chefe 安装会重新构建它
```