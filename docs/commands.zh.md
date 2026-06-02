# 命令

chefe 在统一的 manifest 之上沿用了 pixi 的命令动词。大多数命令都接受一个可选的 `env`，默认为 `default`。

| 命令 | 作用 |
|---|---|
| `chefe init` | 在当前目录中生成一份初始 `chefe.toml` |
| `chefe sync` | 把 `chefe.toml` 编译为 `.chefe/{pixi.toml, package.json, …}` |
| `chefe install [env]` | 先 sync，再为 `env` 配置每个生态系统 |
| `chefe update [env]` | 跨生态系统重新求解到所允许的最新版本 |
| `chefe add <pkg…>` | 把包加入 manifest，再重新 sync |
| `chefe remove <pkg…>` | 在声明它们的任何地方移除包，再重新 sync |
| `chefe tree [env]` | 对比已声明与已安装，每个依赖都在**各自**的生态系统中检查 |
| `chefe run <task> [args…]` | 在环境内运行任务 |
| `chefe x <cmd…>` | 在一次性环境中运行命令，类似 uvx 或 pipx run |
| `chefe shell [env]` | 打开 `env` 中已激活的 shell |
| `chefe global install [name]` | 把 conda 依赖安装到共享的全局 pixi 环境中 |
| `chefe clean` | 移除生成的 `.chefe/` 环境和 manifest |

## init

```sh
chefe init                 # name taken from the current directory
chefe init --name myproj
```

写入一份最小化的 `chefe.toml`，包含当前平台、`conda-forge` 以及 `python >=3.11`。它会拒绝覆盖已存在的 manifest。

## add

Conda 是默认源，通过标志可选择其他生态系统。`--spec` 设置版本（默认为 `*`），`--env` 则指定具名环境。

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

每个已声明的包都会在它被声明的那个生态系统中检查：Conda 对照 pixi 环境，npm 对照 `.chefe/node_modules`，cargo 对照环境的 `.crates.toml`。chefe 把每个包标记为 `✓` 正常、`≠` 版本偏移或 `✗` 缺失，并附上传递依赖的数量。

## run 和 shell

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

与 `uvx` 或 `pipx run` 类似，`chefe x` 会为该工具临时搭建一个环境并运行它，事后不会留下任何 `chefe.toml`。

## global install

```sh
chefe global install          # exposes the conda [deps] as a shared global env
chefe global install mytools
```

## clean

```sh
chefe clean                   # wipe .chefe/, a fresh chefe install rebuilds it
```
