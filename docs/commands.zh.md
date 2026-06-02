# 命令

chefe 在统一的 manifest 之上镜像了 pixi 的各个动词。大多数命令都接受一个可选的 `env`，默认为 `default`。

| 命令 | 作用 |
|---|---|
| `chefe init` | 在当前目录生成一份起步用的 `chefe.toml` |
| `chefe sync` | 把 `chefe.toml` 编译成 `.chefe/{pixi.toml, package.json, …}` |
| `chefe install [env]` | 先 sync，再为 `env` 配置好每一个生态 |
| `chefe update [env]` | 跨生态重新求解到允许范围内的最新版本 |
| `chefe upgrade [pkg…]` | 把 manifest 的 conda + pypi 约束提升到最新，然后 sync |
| `chefe add <pkg…>` | 把包加入 manifest，然后重新 sync |
| `chefe remove <pkg…>` | 在声明它们的任意位置移除包，然后重新 sync |
| `chefe tree [env]` | 已声明 vs 已安装，每个依赖都在**它自己的**生态中核对 |
| `chefe run <task> [args…]` | 在环境内运行一个任务 |
| `chefe x <cmd…>` | 在临时环境中运行一条命令，类似 uvx 或 pipx run |
| `chefe shell [env]` | 打开 `env` 中一个已激活的 shell |
| `chefe global install [name]` | 把每个生态的依赖安装进一个共享的全局环境 |
| `chefe clean` | 移除生成的 `.chefe/` 环境和 manifest |

## init

```sh
chefe init                 # name taken from the current directory
chefe init --name myproj
```

写入一份最小的 `chefe.toml`，包含当前平台、`conda-forge` 和 `python >=3.11`。它不会覆盖已有的 manifest。

## add

Conda 是默认源，用标志可选择另一个生态。`--spec` 设定版本（默认 `*`），`--env` 则指向某个具名环境。

```sh
chefe add ripgrep numpy
chefe add torch --pypi --spec ">=2.6"
chefe add prettier --npm
chefe add vllm --pypi --env serving
```

编辑会保留你的注释和格式。

## tree

```sh
chefe tree
chefe tree serving
```

每个已声明的包都会在它被声明的那个生态中核对。conda 对照 pixi 环境，npm 对照 `.chefe/node_modules`，cargo 对照该环境的 `.crates.toml`。chefe 会把每一项报告为 `✓` 正常、`≠` 漂移或 `✗` 缺失，并附上传递依赖的数量。

## run 与 shell

```sh
chefe run build
chefe shell                # activated shell in the default env
chefe shell serving
```

## x

```sh
chefe x ruff check .                   # run a tool in a throwaway env, no manifest needed
chefe x --with build python -m build   # add extra packages with --with
```

类似 `uvx` 或 `pipx run`，`chefe x` 为工具配置一个临时环境并运行它，不会留下任何 `chefe.toml`。

## global install

把每个生态都配置进一个共享的全局环境，这是 `chefe install` 在「想随处可用的工具」上的对应物。conda 走 `pixi global`，它同时会拉入 python/node/rust 运行时；随后由该全局环境自带的 pip/npm/cargo 来添加 pypi/npm/cargo 依赖。不涉及 uv。

```sh
chefe global install          # every ecosystem's deps into a shared global env
chefe global install mytools  # name the env explicitly
```

## clean

```sh
chefe clean                   # wipe .chefe/, a fresh chefe install rebuilds it
```
