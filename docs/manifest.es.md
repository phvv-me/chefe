# El manifest

Todo reside en un único `chefe.toml`. El encabezado configura el workspace, `[deps]` y las tablas por ecosistema declaran los paquetes, y las superposiciones de plataforma y los entornos nombrados se componen sobre ellos.

## Workspace

```toml
[workspace]
name     = "my-project"
platforms = ["osx-arm64", "linux-64"]
channels = ["conda-forge", "nvidia"]
dotenv   = true                 # leer .env en el entorno, activado por defecto
```

## Dependencias

La tabla `[deps]` básica es **conda**, la fuente predeterminada. Una cadena simple es una especificación de versión, y `*` significa cualquiera.

```toml
[deps]
python = ">=3.11"
nodejs = ">=22"
ripgrep = "*"
pueue  = ">=4"
```

## PyPI

Los paquetes de PyPI son resueltos por pixi-via-`uv` en el **mismo** entorno. `[pypi]` contiene la configuración, `[pypi.deps]` los paquetes y `[pypi.indexes]` índices adicionales nombrados.

```toml
[pypi]
index-strategy = "unsafe-best-match"

[pypi.indexes]
pytorch = "https://download.pytorch.org/whl/cu124"

[pypi.deps]
torch = { version = ">=2.6", index = "pytorch" }
ruff  = ">=0.6"
```

## Otros ecosistemas

Cualquier otro ecosistema es explícito, por lo que no se infiere nada.

```toml
[cargo.deps]
bookokrat = "*"

[npm.deps]
prettier = ">=3"
"@tobilu/qmd" = "*"
```

!!! tip "Los entornos de ejecución se aseguran automáticamente"
    Cada ecosistema necesita su entorno de ejecución de lenguaje para instalarse y ejecutarse, por lo que chefe lo añade desde conda-forge cuando falta. `[pypi.deps]` asegura `python`, `[npm.deps]` asegura `nodejs`, `[cargo.deps]` asegura `rust`, y `[gem.deps]` asegura `ruby`. Declare su propio `python` (u otros) fijado en `[deps]` y chefe no lo tocará. Esto también se aplica por entorno, por lo que un entorno `no-default` que utiliza `[pypi.deps]` aún obtiene su propio `python`.

## Requisitos del sistema

La base de paquetes virtuales de conda utilizada para la resolución multiplataforma, no una carga de módulos.

```toml
[system]
cuda = "13.0"
```

## Variables de entorno

Variables estáticas aplicadas cuando se activa el entorno. `.env` también se lee por defecto, lo cual se puede alternar con `dotenv` en el encabezado.

```toml
[env]
LOG_LEVEL = "info"
CUDA_MODULE_LOADING = "LAZY"
```

## Superposiciones de plataforma

Añada dependencias condicionalmente por plataforma, y estas se compilan a destinos nativos de pixi. Cualquier ámbito se anida bajo `[on.…]`.

```toml
[on.linux.deps]
cupy = ">=13"

[on.linux-aarch64.pypi.deps]
some-arm-wheel = "*"
```

## Entornos nombrados

Componga entornos adicionales, como las características de pixi. `no-default = true` excluye las dependencias base.

```toml
[envs.serving]
no-default = true

[envs.serving.pypi.deps]
vllm = ">=0.6"
```

Instale o inspeccione uno con `chefe install serving` o `chefe tree serving`.

## Tareas

Comandos nombrados que se ejecutan dentro del entorno, a los que se accede con `chefe run <task>`.

```toml
[tasks]
serve = { run = "python -m my_project.server", depends = ["build"] }
build = "python -m my_project.build"
```