<div class="hero" markdown>

![chefe — one manifest for every package manager](assets/banner.svg){ .hero-banner }

# chefe { .visually-hidden }

</div>

## 安装

```sh
curl -fsSL https://phvv.me/chefe/install.sh | sh
```

这将安装 [pixi](https://pixi.sh)（chefe 编译所依赖的引擎）以及 chefe 本身。更倾向于使用原生包？请使用 `pip install chefe` 或 `uv tool install chefe`。

## 它是什么

Conda、PyPI、npm、cargo。真正的项目往往需要同时使用多种工具，分散在 `pixi.toml`、`package.json` 和 `Cargo.toml` 中。chefe 是你的主厨。你只需编写**一份 `chefe.toml`** 配方，它就会将每个原生 manifest 编译到 `.chefe/` 目录下，运行相应的工具，并将它们整合为一个单一的环境。它从不重新实现解析器，而是指挥各个“厨师”工作。

<div class="grid cards" markdown>

- :material-silverware-variant: **一份配方**

    将所有生态系统整合在单一的 `chefe.toml` 中。无需再同时维护四个 manifest。

- :material-cog-transfer-outline: **原生输出**

    编译为真实的 `pixi.toml`、`package.json` 等文件。由实际的工具负责依赖解析。

- :material-source-branch: **可组合**

    平台覆盖层和命名环境可以像 pixi 的特性（features）一样叠加。

- :material-broom: **自包含**

    整个环境都存在于 `.chefe/` 中，因此只需一条命令即可将其清除。

</div>

!!! warning "chefe 处于早期阶段 (`0.0.x`)"
    manifest 格式和命令可能仍会发生变化。

## 快速入门

```sh
chefe init                 # 初始化一个 chefe.toml
chefe add ripgrep          # 添加依赖，使用 --pypi / --cargo / --npm 指定其他生态
chefe install              # 同时配置所有生态系统
chefe tree                 # 查看每个生态系统中已声明与已安装的依赖
```

## 它是如何协同工作的

```mermaid
flowchart LR
    M(["chefe.toml"]):::brand
    M -->|chefe sync| P["pixi.toml"] --> PIXI["pixi<br/>conda · PyPI via uv"] --> ENV
    M -->|chefe sync| N["package.json"] --> NPM["npm"] --> ENV
    M -->|chefe sync| C["cargo / gem specs"] --> CARGO["cargo · gem"] --> ENV
    ENV(["one activated<br/>environment"]):::brandDark
    classDef brand fill:#eab308,stroke:#1a1a1a,stroke-width:2px,color:#1a1a1a;
    classDef brandDark fill:#1a1a1a,stroke:#eab308,stroke-width:2px,color:#ffffff;
```

- **结构**由 chefe 的 schema 进行验证，而**包规范**则保留为每个工具的职责。
- 通过 `chefe add` 和 `chefe remove` 编辑 `chefe.toml` 可以保留你的注释和格式。
- `pixi`（内置 `uv`）是 conda 和 PyPI 的底层引擎，而其他生态系统则是其上层轻量且显式的层级。

接下来，请参阅 [manifest 参考](manifest.md) 和 [命令参考](commands.md)。

## 背景

主厨从不独自烹饪每一道菜。他们编写配方并管理生产线，由各岗位的厨师负责具体工作。分散的包管理器就是那条生产线，而 chefe 则通过一份配方指挥它们。🧑‍🍳