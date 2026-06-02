# El manifest

Todo vive en un solo `chefe.toml`. El encabezado configura el workspace, `[deps]` y las tablas por ecosistema declaran los paquetes, y las superposiciones por plataforma y los entornos con nombre se componen por encima.

## Workspace

```toml
[workspace]
name     = "my-project"
platforms = ["osx-arm64", "linux-64"]
channels = ["conda-forge", "nvidia"]
dotenv   = true                 # read .env into the environment, on by default
```

## Dependencias

La tabla `[deps]` por sí sola es **conda**, la fuente por defecto. Una cadena simple es una especificación de versión, y `*` significa cualquier versión.

```toml
[deps]
python = ">=3.11"
nodejs = ">=22"
ripgrep = "*"
pueue  = ">=4"
```

## PyPI

Los paquetes de PyPI los resuelve pixi mediante `uv` en el **mismo** entorno. `[pypi]` contiene la configuración, `[pypi.deps]` los paquetes, y `[pypi.indexes]` índices extra con nombre.

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

Todos los demás ecosistemas son explícitos, así que nada se infiere.

```toml
[cargo.deps]
bookokrat = "*"

[npm.deps]
prettier = ">=3"
"@tobilu/qmd" = "*"
```

!!! tip "Los runtimes se garantizan automáticamente"
    Cada ecosistema necesita su runtime de lenguaje para instalar y ejecutar, así que chefe lo agrega desde
    conda-forge cuando falta. `[pypi.deps]` garantiza `python`, `[npm.deps]` garantiza `nodejs`,
    `[cargo.deps]` garantiza `rust`, y `[gem.deps]` garantiza `ruby`. Declara tu propio `python`
    fijado (u otros) en `[deps]` y chefe lo respeta. Esto también aplica por entorno,
    así que un entorno `no-default` que usa `[pypi.deps]` igual obtiene su propio `python`.

## Requisitos del sistema

El mínimo de paquetes virtuales de conda que se usa para la resolución multiplataforma, no una carga de módulos.

```toml
[system]
cuda = "13.0"
```

## Variables de entorno

Variables estáticas aplicadas cuando el entorno se activa. `.env` también se lee por defecto, controlado con `dotenv` en el encabezado.

```toml
[env]
LOG_LEVEL = "info"
CUDA_MODULE_LOADING = "LAZY"
```

## Superposiciones por plataforma

Agrega dependencias condicionalmente por plataforma, y compilan a targets nativos de pixi. Cualquier ámbito se anida bajo `[on.…]`.

```toml
[on.linux.deps]
cupy = ">=13"

[on.linux-aarch64.pypi.deps]
some-arm-wheel = "*"
```

## Entornos con nombre

Compón entornos adicionales, como los features de pixi. `no-default = true` excluye las dependencias base.

```toml
[envs.serving]
no-default = true

[envs.serving.pypi.deps]
vllm = ">=0.6"
```

Instala o inspecciona uno con `chefe install serving` o `chefe tree serving`.

## Tareas

Comandos con nombre que se ejecutan dentro del entorno, accesibles con `chefe run <task>`.

```toml
[tasks]
serve = { run = "python -m my_project.server", depends = ["build"] }
build = "python -m my_project.build"
```
