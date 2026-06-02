# Como funciona

O `chefe sync` compila seu único `chefe.toml` nos manifests nativos dentro de `.chefe/`, e então o `chefe install` entrega cada um à ferramenta real, para que elas resolvam e construam um único ambiente compartilhado.

```mermaid
flowchart TB
    subgraph recipe["uma receita (chefe.toml)"]
        direction LR
        D["[deps]<br/>conda"]
        PY["[pypi.deps]"]
        NP["[npm.deps]"]
        CG["[cargo.deps]"]
    end

    subgraph compiled["chefe sync gera .chefe/"]
        direction LR
        PT["pixi.toml"]
        PJ["package.json"]
    end

    subgraph solve["chefe install executa as ferramentas reais"]
        direction LR
        PIXI["pixi<br/>conda-forge"]
        UV["uv<br/>dentro do pixi"]
        NPM["npm"]
        CARGO["cargo<br/>via pixi run cargo"]
    end

    ENV(["um ambiente ativado<br/>prefixo .chefe/ no PATH"]):::brand

    D --> PT
    PY --> PT
    NP --> PJ
    CG -. sem arquivo, instala no local .-> CARGO

    PT --> PIXI
    PIXI --> UV
    PJ --> NPM

    PIXI --> ENV
    UV --> ENV
    NPM --> ENV
    CARGO --> ENV

    classDef brand fill:#eab308,stroke:#1a1a1a,stroke-width:2px,color:#1a1a1a;
```

- A **estrutura** é validada pelo schema do chefe, enquanto as **especificações de pacotes** continuam sendo trabalho de cada ferramenta.
- Editar o `chefe.toml` através do `chefe add` e do `chefe remove` preserva seus comentários e sua formatação.
- O `pixi` (com o `uv` dentro dele) é o motor profundo para conda e PyPI, e os outros ecossistemas são camadas finas e explícitas por cima.

## Início rápido

```sh
chefe init                 # scaffold a chefe.toml
chefe add ripgrep          # add deps, use --pypi / --cargo / --npm for others
chefe install              # provision every ecosystem at once
chefe tree                 # what's declared vs installed, per ecosystem
```

A seguir, a [referência do manifest](manifest.md) e a [referência de comandos](commands.md).
