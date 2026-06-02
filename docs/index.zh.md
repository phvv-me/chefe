# chefe

一份 manifest，搞定所有包管理器。

Conda、PyPI、npm、cargo。真实的项目往往同时需要好几个，零散地分布在 `pixi.toml`、`package.json` 和 `Cargo.toml` 之间。**chefe** 就是那位主厨：你只写**一份 `chefe.toml`** 食谱，它会在 `.chefe/` 下编译出每一份原生 manifest，调用真正的工具，最后把它们摆盘成一个统一的环境。它从不重新实现求解器，它只负责指挥后厨。

<div class="grid cards" markdown>

- :material-silverware-variant: **一份食谱**

    所有生态都写进一份 `chefe.toml`。不必再同时摆弄四份 manifest。

- :material-cog-transfer-outline: **原生输出**

    编译成真正的 `pixi.toml`、`package.json` 等文件。真正的工具来做求解。

- :material-source-branch: **可组合**

    平台叠加层和具名环境像 pixi feature 一样层层堆叠。

- :material-broom: **自包含**

    整个环境都存在 `.chefe/` 里，一条命令即可清除。

</div>

## 安装

```sh
curl -fsSL https://phvv.me/chefe/install.sh | sh
```

它只需要 [pixi](https://pixi.sh)，也就是 chefe 编译的目标引擎，同时它也提供了用来安装 chefe 的 Python。更想要原始包？`pip install chefe`。

```toml title="chefe.toml"
[workspace]
name = "my-project"

[deps]                 # conda, the default source
python  = ">=3.12"
ripgrep = "*"

[pypi.deps]
torch = ">=2.6"

[npm.deps]
prettier = ">=3"
```

!!! warning "chefe 尚在早期阶段（`0.0.x`）"
    manifest 格式和命令仍可能发生变化。

## 下一步

<div class="grid cards" markdown>

- [:material-cogs: **工作原理**](how-it-works.md) — 编译与运行的流水线。
- [:material-console: **命令**](commands.md) — 完整的 CLI。
- [:material-file-document-outline: **Manifest**](manifest.md) — 每一个 `chefe.toml` 表项。
- [:material-test-tube: **示例**](examples.md) — 一份真实世界的 monorepo 食谱。

</div>

## 由来

主厨从不独自烹制每一道菜。他写下食谱、统筹整条出菜线，每位厨师各守一个工位。零散的包管理器就是这条出菜线，于是 chefe 用一份食谱来指挥它们。🧑‍🍳
