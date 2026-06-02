# chefe

Un manifest para todos los gestores de paquetes.

Conda, PyPI, npm, cargo. Los proyectos reales necesitan varios a la vez, dispersos entre `pixi.toml`, `package.json` y `Cargo.toml`. **chefe** es el chef de cocina: escribes **una receta `chefe.toml`**, compila cada manifest nativo dentro de `.chefe/`, ejecuta las herramientas reales y las sirve como un solo entorno. Nunca reimplementa un solver. Dirige a los cocineros.

<div class="grid cards" markdown>

- :material-silverware-variant: **Una receta**

    Cada ecosistema en un solo `chefe.toml`. Se acabó hacer malabares con cuatro manifests.

- :material-cog-transfer-outline: **Salida nativa**

    Compila a `pixi.toml`, `package.json` y compañía reales. Las herramientas de verdad hacen la resolución.

- :material-source-branch: **Componible**

    Las superposiciones por plataforma y los entornos con nombre se apilan como las features de pixi.

- :material-broom: **Autocontenido**

    Todo el entorno vive en `.chefe/`, así que un solo comando lo borra.

</div>

## Instalación

```sh
curl -fsSL https://phvv.me/chefe/install.sh | sh
```

Solo necesita [pixi](https://pixi.sh), el motor al que chefe compila, que además provee el Python con el que instala chefe. ¿Prefieres el paquete directo? `pip install chefe`.

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

!!! warning "chefe está en etapa temprana (`0.0.x`)"
    El formato del manifest y los comandos todavía pueden cambiar.

## Siguiente

<div class="grid cards" markdown>

- [:material-cogs: **Cómo funciona**](how-it-works.md) — el pipeline de compilar y ejecutar.
- [:material-console: **Comandos**](commands.md) — el CLI completo.
- [:material-file-document-outline: **Manifest**](manifest.md) — cada tabla de `chefe.toml`.
- [:material-test-tube: **Ejemplos**](examples.md) — una receta de monorepo del mundo real.

</div>

## Historia

Un chef de cocina nunca prepara cada plato solo. Escribe la receta y dirige la línea, y cada cocinero trabaja su estación. Los gestores de paquetes dispersos son esa línea, así que chefe los dirige desde una sola receta. 🧑‍🍳
