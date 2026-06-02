<div class="hero" markdown>

![chefe — one manifest for every package manager](assets/banner.svg){ .hero-banner }

# chefe { .visually-hidden }

</div>

## Instalación

```sh
curl -fsSL https://phvv.me/chefe/install.sh | sh
```

Esto instala [pixi](https://pixi.sh) (el motor al que compila chefe) y a chefe mismo. ¿Prefieres el paquete original? Usa `pip install chefe` o `uv tool install chefe`.

## Qué es

Conda, PyPI, npm, cargo. Los proyectos reales necesitan varios a la vez, dispersos entre `pixi.toml`, `package.json` y `Cargo.toml`. chefe es el jefe de cocina. Tú escribes **una receta `chefe.toml`**, él compila cada manifest nativo bajo `.chefe/`, ejecuta las herramientas reales y los sirve como un solo entorno. Nunca vuelve a implementar un resolvedor. Él dirige a los cocineros.

<div class="grid cards" markdown>

- :material-silverware-variant: **Una receta**

    Cada ecosistema en un solo `chefe.toml`. No más malabares con cuatro manifests.

- :material-cog-transfer-outline: **Salida nativa**

    Compila a `pixi.toml`, `package.json` y similares reales. Las herramientas reales hacen la resolución.

- :material-source-branch: **Componible**

    Las superposiciones de plataforma y los entornos con nombre se apilan como las características de pixi.

- :material-broom: **Autocontenido**

    Todo el entorno vive en `.chefe/`, así que un comando lo elimina por completo.

</div>

!!! warning "chefe está en etapa temprana (`0.0.x`)"
    El formato del manifest y los comandos aún pueden cambiar.

## Inicio rápido

```sh
chefe init                 # crea la estructura de un chefe.toml
chefe add ripgrep          # añade dependencias, usa --pypi / --cargo / --npm para otras
chefe install              # aprovisiona cada ecosistema a la vez
chefe tree                 # qué está declarado vs instalado, por ecosistema
```

## Cómo encaja todo

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

- La **estructura** es validada por el esquema de chefe, mientras que las **especificaciones de los paquetes** siguen siendo trabajo de cada herramienta.
- Editar `chefe.toml` a través de `chefe add` y `chefe remove` mantiene tus comentarios y formato.
- `pixi` (con `uv` dentro) es el motor profundo para conda y PyPI, y los otros ecosistemas son capas delgadas y explícitas sobre él.

A continuación, la [referencia del manifest](manifest.md) y la [referencia de comandos](commands.md).

## Historia

Un jefe de cocina nunca prepara cada plato solo. Escribe la receta y dirige la línea, y cada cocinero trabaja en su estación. Los gestores de paquetes dispersos son esa línea, así que chefe los dirige desde una sola receta. 🧑‍🍳