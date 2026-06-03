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

## Elegir el gestor de npm

El ecosistema npm es el registro de npm, y `manager` dentro de `[npm]` nombra el binario que lo
instala. El `package.json` compilado es el mismo sin importar cuál elija un proyecto, y chefe
ejecuta la herramienta nombrada dentro del entorno generado, así que funciona cualquier gestor de
paquetes que instale en su directorio de trabajo, incluso uno que chefe nunca haya conocido.

```toml
[npm]
manager = "pnpm"   # npm por defecto; pnpm, bun, aube, yarn o cualquier otro binario

[npm.deps]
svelte = ">=5"
```

npm es el valor por defecto, así que una tabla `[npm.deps]` existente sigue instalando con npm.
Nombrar otra herramienta cambia solo el binario que chefe ejecuta, nunca las dependencias, el
registro ni el archivo.

!!! note "El gestor debe estar en el PATH"
    chefe garantiza `nodejs` para el ecosistema npm; el binario del gestor lo provees tú. pnpm está
    en conda-forge, así que agregarlo a `[deps]` mantiene reproducible la instalación, mientras que
    herramientas como bun o aube vienen fuera de conda y se instalan una vez en la máquina.

## Aplicaciones JavaScript

Por defecto `[npm.deps]` se instala como herramientas dentro de `.chefe/`, junto al entorno conda.
Una aplicación define `app = true`, y chefe instala en la raíz del proyecto y escribe ahí un
`package.json` completo, para que Vite, SvelteKit y los demás resuelvan `node_modules` como siempre.

```toml
[npm]
manager = "pnpm"
app = true

[npm.deps]
svelte = ">=5"
vite = ">=8"

[npm.package]
type = "module"
pnpm = { onlyBuiltDependencies = ["esbuild", "workerd"] }
```

`[npm.package]` se fusiona en `package.json` tal cual, así que cualquier campo que una herramienta
espere pasa sin cambios, desde `type` y `engines` hasta los ajustes propios de un gestor como
`onlyBuiltDependencies` de pnpm. chefe escribe el archivo, así que `chefe.toml` sigue siendo lo
único que editas y un `package.json` generado es un artefacto de build que puedes ignorar en git.

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
