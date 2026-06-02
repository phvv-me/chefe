# How it works

`chefe sync` compiles your one `chefe.toml` into the native manifests under `.chefe/`, then `chefe install` hands each one to the real tool so they solve and build a single shared environment.

```mermaid
flowchart TB
    subgraph recipe["one recipe (chefe.toml)"]
        direction LR
        D["[deps]<br/>conda"]
        PY["[pypi.deps]"]
        NP["[npm.deps]"]
        CG["[cargo.deps]"]
    end

    subgraph compiled["chefe sync generates .chefe/"]
        direction LR
        PT["pixi.toml"]
        PJ["package.json"]
    end

    subgraph solve["chefe install runs the real tools"]
        direction LR
        PIXI["pixi<br/>conda-forge"]
        UV["uv<br/>inside pixi"]
        NPM["npm"]
        CARGO["cargo<br/>via pixi run cargo"]
    end

    ENV(["one activated environment<br/>.chefe/ prefix on PATH"]):::brand

    D --> PT
    PY --> PT
    NP --> PJ
    CG -. no file, installs in-place .-> CARGO

    PT --> PIXI
    PIXI --> UV
    PJ --> NPM

    PIXI --> ENV
    UV --> ENV
    NPM --> ENV
    CARGO --> ENV

    classDef brand fill:#eab308,stroke:#1a1a1a,stroke-width:2px,color:#1a1a1a;
```

- **Structure** is validated by chefe's schema, while **package specs** stay each tool's job.
- Editing `chefe.toml` through `chefe add` and `chefe remove` keeps your comments and formatting.
- `pixi` (with `uv` inside it) is the deep engine for conda and PyPI, and the other ecosystems are thin, explicit layers on top.

## Quickstart

```sh
chefe init                 # scaffold a chefe.toml
chefe add ripgrep          # add deps, use --pypi / --cargo / --npm for others
chefe install              # provision every ecosystem at once
chefe tree                 # what's declared vs installed, per ecosystem
```

Next, the [manifest reference](manifest.md) and the [command reference](commands.md).
