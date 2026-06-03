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

La tabla simple `[deps]` es **conda**, el resolver por defecto. Una cadena suelta es un spec de versión, y `*` significa cualquiera.

```toml
[deps]
python = ">=3.11"
nodejs = ">=22"
ripgrep = "*"
pueue  = ">=4"
```

## Python

Los paquetes Python los resuelve pixi-vía-`uv` en el **mismo** entorno. `[python]` contiene la configuración, `[python.deps]` los paquetes, y `[python.indexes]` índices extra con nombre.

```toml
[python]
index-strategy = "unsafe-best-match"

[python.indexes]
pytorch = "https://download.pytorch.org/whl/cu124"

[python.deps]
torch = { version = ">=2.6", index = "pytorch" }
ruff  = ">=0.6"
```

## Toolchains por runtime

Todos los demás lenguajes/toolchains son explícitos, así que nada se infiere.

```toml
[rust.deps]
bookokrat = "*"

[nodejs.dev.deps]
prettier = ">=3"
"@tobilu/qmd" = "*"
```

!!! tip "Los runtimes se garantizan automáticamente"
    Cada ecosistema necesita el runtime de su lenguaje para instalar y ejecutar, así que chefe lo agrega desde
    conda-forge cuando falta. `[python.deps]` garantiza `python`.
    Toolchains como `nodejs` y `rust` deben declararse en `[deps]`. Declara tu propio `python` fijado
    (u otros) en `[deps]` y chefe lo deja en paz. Esto también aplica por entorno,
    así que un entorno `no-default` que usa `[python.deps]` igual obtiene su propio `python`.

## Elegir el gestor de npm

El ecosistema Node.js usa el registro npm, y `manager` dentro de `[nodejs]` nombra el binario que lo
instala. El `package.json` compilado es el mismo sin importar cuál elija un proyecto, y chefe
ejecuta la herramienta nombrada dentro del entorno generado, así que funciona cualquier gestor de
paquetes que instale en su directorio de trabajo, incluso uno que chefe nunca haya conocido.

```toml
[nodejs]
manager = "pnpm"   # npm por defecto; pnpm, yarn o cualquier binario compatible

[nodejs.deps]
svelte = ">=5"
```

`npm` es el valor por defecto, así que una tabla `[nodejs.deps]` instala con npm si `manager` no se define.
Nombrar otra herramienta cambia solo el binario que chefe ejecuta, nunca las dependencias, el
registro ni el archivo.

!!! note "El gestor debe estar en el PATH"
    Declara `nodejs` en `[deps]`; el binario del gestor lo provees tú. Si `manager` nombra una
    herramienta ausente, el comando real falla cuando se ejecuta.

## Aplicaciones JavaScript

Por defecto `[nodejs.deps]` se instala como herramientas dentro de `.chefe/`, junto al entorno conda.
Una aplicación define `app = true`, y chefe instala en la raíz del proyecto y escribe ahí un
`package.json` completo, para que Vite, SvelteKit y los demás resuelvan `node_modules` como siempre.

```toml
[nodejs]
manager = "pnpm"
app = true

[nodejs.deps]
svelte = ">=5"
vite = ">=8"

[nodejs.package]
type = "module"
pnpm = { onlyBuiltDependencies = ["esbuild", "workerd"] }
```

`[nodejs.package]` se fusiona en `package.json` tal cual, así que cualquier campo que una herramienta
espere pasa sin cambios, desde `type` y `engines` hasta los ajustes propios de un gestor como
`onlyBuiltDependencies` de pnpm. chefe escribe el archivo, así que `chefe.toml` sigue siendo lo
único que editas y un `package.json` generado es un artefacto de build que puedes ignorar en git.

## Dependencias de desarrollo

`[dev.*]` refleja el scope base para herramientas que necesitas para construir y probar pero no
para ejecutar. Cada grupo compila al mecanismo de desarrollo propio de su ecosistema, y
`chefe install` las provisiona por defecto.

```toml
[dev.deps]            # herramientas de desarrollo conda
ruff = "*"

[dev.python.deps]       # herramientas de desarrollo Python
pytest = ">=8"

[nodejs.dev.deps]     # -> devDependencies de package.json
vite = ">=8"
```

`[nodejs.dev.deps]` va a `devDependencies`, mientras que `[dev.deps]` y `[dev.python.deps]` se convierten
en una feature `dev` añadida al entorno por defecto, así que tus linters y tu corredor de pruebas se
instalan junto a las dependencias de ejecución. Esto es más ligero que un `[envs.dev]` completo, que
es un entorno separado con su propia resolución.

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

python = "*"

[on.linux-aarch64.python.deps]
some-arm-wheel = "*"
```

## Entornos con nombre

Compón entornos extra, como las features de pixi. `no-default = true` excluye las deps base, y `platforms` restringe el entorno a donde puede construirse (así un entorno de GPU se omite al resolver en una laptop).

```toml

python = "*"

[envs.serving.python.deps]
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
