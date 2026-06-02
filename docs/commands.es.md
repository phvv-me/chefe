# Comandos

chefe refleja los verbos de pixi sobre el manifest unificado. La mayoría de los comandos aceptan un `env` opcional que por defecto es `default`.

| comando | qué hace |
|---|---|
| `chefe init` | genera un `chefe.toml` inicial en el directorio actual |
| `chefe sync` | compila `chefe.toml` en `.chefe/{pixi.toml, package.json, …}` |
| `chefe install [env]` | sincroniza y luego aprovisiona cada ecosistema para `env` |
| `chefe update [env]` | vuelve a resolver a las versiones más nuevas permitidas en todos los ecosistemas |
| `chefe add <pkg…>` | agrega paquetes al manifest y vuelve a sincronizar |
| `chefe remove <pkg…>` | elimina paquetes en donde sea que estén declarados y vuelve a sincronizar |
| `chefe tree [env]` | declarado vs instalado, cada dependencia verificada en **su propio** ecosistema |
| `chefe run <task> [args…]` | ejecuta una tarea dentro del entorno |
| `chefe x <cmd…>` | ejecuta un comando en un entorno desechable, como uvx o pipx run |
| `chefe shell [env]` | abre una shell activada en `env` |
| `chefe global install [name]` | instala las dependencias de conda en el entorno global compartido de pixi |
| `chefe clean` | elimina el entorno y los manifests generados en `.chefe/` |

## init

```sh
chefe init                 # name taken from the current directory
chefe init --name myproj
```

Escribe un `chefe.toml` mínimo con la plataforma actual, `conda-forge` y `python >=3.11`. Nunca sobrescribe un manifest existente.

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

Cada paquete declarado se verifica contra el ecosistema en el que fue declarado. Conda se verifica contra el entorno de pixi, npm contra `.chefe/node_modules` y cargo contra el `.crates.toml` del entorno. chefe reporta cada uno como `✓` ok, `≠` desviación o `✗` faltante, junto con un conteo transitivo.

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

```sh
chefe global install          # exposes the conda [deps] as a shared global env
chefe global install mytools
```

## clean

```sh
chefe clean                   # wipe .chefe/, a fresh chefe install rebuilds it
```
