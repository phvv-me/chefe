# Comandos

chefe refleja los verbos de pixi sobre el manifest unificado. La mayoría de los comandos toman un `env` opcional que por defecto es `default`.

| comando | qué hace |
|---|---|
| `chefe init` | scaffold de un `chefe.toml` inicial en el directorio actual |
| `chefe sync` | compila `chefe.toml` en `.chefe/{pixi.toml, package.json, …}` |
| `chefe install [env]` | sync y luego aprovisiona cada ecosistema para `env` |
| `chefe update [env]` | vuelve a resolver a las versiones más nuevas permitidas en todos los ecosistemas |
| `chefe upgrade [pkg…]` | sube las restricciones de conda + pypi del manifest a lo más reciente, luego sync |
| `chefe add <pkg…>` | agrega paquetes al manifest, luego vuelve a sincronizar |
| `chefe remove <pkg…>` | elimina paquetes donde sea que estén declarados, luego vuelve a sincronizar |
| `chefe tree [env]` | declarado vs instalado, cada dep verificada en **su propio** ecosistema |
| `chefe run <task> [args…]` | ejecuta una tarea dentro del entorno |
| `chefe x <cmd…>` | ejecuta un comando en un entorno desechable, como uvx o pipx run |
| `chefe shell [env]` | abre una shell activada en `env` |
| `chefe global install [name]` | instala las deps de cada ecosistema en un entorno global compartido |
| `chefe clean` | elimina el entorno `.chefe/` generado y los manifests |

## init

```sh
chefe init                 # name taken from the current directory
chefe init --name myproj
```

Escribe un `chefe.toml` mínimo con la plataforma actual, `conda-forge` y `python >=3.11`. Se niega a sobrescribir un manifest existente.

## add

Conda es la fuente por defecto, y los flags eligen otro ecosistema. `--spec` define la versión (por defecto `*`), mientras que `--env` apunta a un entorno con nombre.

```sh
chefe add ripgrep numpy
chefe add torch --pypi --spec ">=2.6"
chefe add prettier --npm
chefe add vllm --pypi --env serving
```

Las ediciones conservan tus comentarios y formato.

## tree

```sh
chefe tree
chefe tree serving
```

Cada paquete declarado se verifica contra el ecosistema en el que fue declarado. Conda va contra el entorno de pixi, npm contra `.chefe/node_modules`, y cargo contra el `.crates.toml` del entorno. chefe reporta cada uno como `✓` ok, `≠` desviación, o `✗` faltante, con un conteo transitivo.

## run y shell

```sh
chefe run build
chefe shell                # activated shell in the default env
chefe shell serving
```

## x

```sh
chefe x ruff check .                   # run a tool in a throwaway env, no manifest needed
chefe x --with build python -m build   # add extra packages with --with
```

Como `uvx` o `pipx run`, `chefe x` aprovisiona un entorno efímero para la herramienta y la ejecuta, sin dejar ningún `chefe.toml` atrás.

## global install

Aprovisiona cada ecosistema en un solo entorno global compartido, el equivalente de `chefe install` para herramientas que quieres en todas partes. conda pasa por `pixi global`, que además trae los runtimes de python/node/rust; luego el propio pip/npm/cargo del entorno global agrega las deps de pypi/npm/cargo. Sin uv de por medio.

```sh
chefe global install          # every ecosystem's deps into a shared global env
chefe global install mytools  # name the env explicitly
```

## clean

```sh
chefe clean                   # wipe .chefe/, a fresh chefe install rebuilds it
```
