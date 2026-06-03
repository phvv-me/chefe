# Cómo funciona

`chefe sync` compila tu único `chefe.toml` en los manifests nativos dentro de `.chefe/`, y luego `chefe install` le entrega cada uno a la herramienta real para que resuelvan y construyan un solo entorno compartido.

```mermaid
flowchart TB
    subgraph recipe["una receta (chefe.toml)"]
        direction LR
        D["[deps]<br/>conda"]
        PY["[python.deps]"]
        NP["[nodejs.deps]"]
        CG["[rust.deps]"]
    end

    subgraph compiled["chefe sync genera .chefe/"]
        direction LR
        PT["pixi.toml"]
        PJ["package.json"]
    end

    subgraph solve["chefe install ejecuta las herramientas reales"]
        direction LR
        PIXI["pixi<br/>conda-forge"]
        UV["uv<br/>dentro de pixi"]
        NPM["npm"]
        CARGO["cargo<br/>via pixi run cargo"]
    end

    ENV(["un entorno activado<br/>prefijo .chefe/ en PATH"]):::brand

    D --> PT
    PY --> PT
    NP --> PJ
    CG -. sin archivo, instala en sitio .-> CARGO

    PT --> PIXI
    PIXI --> UV
    PJ --> NPM

    PIXI --> ENV
    UV --> ENV
    NPM --> ENV
    CARGO --> ENV

    classDef brand fill:#eab308,stroke:#1a1a1a,stroke-width:2px,color:#1a1a1a;
```

- La **estructura** la valida el esquema de chefe, mientras que los **specs de paquetes** siguen siendo tarea de cada herramienta.
- Editar `chefe.toml` a través de `chefe add` y `chefe remove` conserva tus comentarios y formato.
- `pixi` (con `uv` dentro) es el motor profundo para conda y Python packages, y los demás lenguajes/toolchains son capas delgadas y explícitas por encima.

## Inicio rápido

```sh
chefe init                 # scaffold a chefe.toml
chefe add ripgrep          # conda is the default resolver
chefe add torch -l python
chefe add prettier -l nodejs
chefe install              # provision every language/toolchain at once
chefe tree                 # what's declared vs installed, per language/toolchain
```

A continuación, la [referencia del manifest](manifest.md) y la [referencia de comandos](commands.md).
