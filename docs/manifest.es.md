# El manifest

Todo vive en un solo `chefe.toml`. El encabezado configura el workspace, `[deps]` y las tablas por ecosistema declaran paquetes, y las superposiciones por plataforma y los entornos con nombre se componen por encima.

## Workspace

```toml
[workspace]
name     = "my-project"
platforms = ["osx-arm64", "linux-64"]
channels = ["conda-forge", "nvidia"]
dotenv   = true                 # read .env into the environment, on by default
```

## Dependencias

La tabla simple `[deps]` es **conda**, la fuente por defecto. Una cadena suelta es un spec de versión, y `*` significa cualquiera.

```toml
[deps]
python = ">=3.11"
nodejs = ">=22"
ripgrep = "*"
pueue  = ">=4"
```

## PyPI

Los paquetes de PyPI los resuelve pixi-vía-`uv` en el **mismo** entorno. `[pypi]` contiene la configuración, `[pypi.deps]` los paquetes, y `[pypi.indexes]` índices extra con nombre.

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
    Cada ecosistema necesita el runtime de su lenguaje para instalar y ejecutar, así que chefe lo agrega desde
    conda-forge cuando falta. `[pypi.deps]` garantiza `python`, `[npm.deps]` garantiza `nodejs`,
    `[cargo.deps]` garantiza `rust`, y `[gem.deps]` garantiza `ruby`. Declara tu propio `python` fijado
    (u otros) en `[deps]` y chefe lo deja en paz. Esto también aplica por entorno,
    así que un entorno `no-default` que usa `[pypi.deps]` igual obtiene su propio `python`.

## Requisitos del sistema

El piso de paquetes virtuales de conda usado para la resolución multiplataforma, no una carga de módulo.

```toml
[system]
cuda = "13.0"
```

## Variables de entorno

Variables estáticas que se aplican cuando el entorno se activa. `.env` también se lee por defecto, conmutado con `dotenv` en el encabezado.

```toml
[env]
LOG_LEVEL = "info"
CUDA_MODULE_LOADING = "LAZY"
```

## Scripts de activación

Scripts de shell que se ejecutan (sourced) cuando el entorno se activa, para configuración que las variables de entorno estáticas no pueden expresar (rutas calculadas, symlinks de librerías). Compilan a los `[activation] scripts` de pixi; una ruta relativa a la raíz del repo sigue funcionando desde el `.chefe/` generado.

```toml
[activation]
scripts = ["scripts/activate.sh"]
```

## Superposiciones por plataforma

Agrega deps condicionalmente por plataforma, y compilan a targets nativos de pixi. Cualquier scope se anida bajo `[on.…]`.

```toml
[on.linux.deps]
cupy = ">=13"

[on.linux-aarch64.pypi.deps]
some-arm-wheel = "*"
```

## Entornos con nombre

Compón entornos extra, como las features de pixi. `no-default = true` excluye las deps base, y `platforms` restringe el entorno a donde puede construirse (así un entorno de GPU se omite al resolver en una laptop).

```toml
[envs.serving]
no-default = true
platforms  = ["linux-64", "linux-aarch64"]

[envs.serving.pypi.deps]
vllm = ">=0.6"
```

Instala o inspecciona uno con `chefe install serving` o `chefe tree serving`.

## Tareas

Comandos con nombre que se ejecutan dentro del entorno, alcanzados con `chefe run <task>`. Ejecutan *código*, nunca instalan dependencias. Cada paquete pertenece a la tabla `[<eco>.deps]` de su ecosistema para que `chefe install` y `chefe global` lo administren. Una tarea que invoca `npm install -g` o `cargo install` es el antipatrón que chefe reemplaza.

```toml
[tasks]
serve = { run = "python -m my_project.server", depends = ["build"] }
build = "python -m my_project.build"
```
