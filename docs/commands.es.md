# Comandos

chefe replica los verbos de pixi sobre el manifest unificado. La mayoría de los comandos aceptan un `env` opcional que utiliza `default` por defecto.

| comando | qué hace |
|---|---|
| `chefe init` | crea un `chefe.toml` inicial en el directorio actual |
| `chefe sync` | compila `chefe.toml` en `.chefe/{pixi.toml, package.json, …}` |
| `chefe install [env]` | sincroniza y luego aprovisiona cada ecosistema para el `env` |
| `chefe update [env]` | resuelve nuevamente a las versiones permitidas más recientes en todos los ecosistemas |
| `chefe add <pkg…>` | agrega paquetes al manifest y luego vuelve a sincronizar |
| `chefe remove <pkg…>` | elimina paquetes donde sea que estén declarados y luego vuelve a sincronizar |
| `chefe tree [env]` | declarado vs instalado, cada dependencia verificada en **su propio** ecosistema |
| `chefe run <task> [args…]` | ejecuta una tarea dentro del entorno |
| `chefe x <cmd…>` | ejecuta un comando en un entorno desechable, como uvx o pipx run |
| `chefe shell [env]` | abre una shell activada en el `env` |
| `chefe global install [name]` | instala las dependencias de conda en el entorno global compartido de pixi |
| `chefe clean` | elimina el entorno `.chefe/` generado y los manifests |

## init

```sh
chefe init                 # nombre tomado del directorio actual
chefe init --name myproj
```

Escribe un `chefe.toml` mínimo con la plataforma actual, `conda-forge` y `python >=3.11`. Se niega a sobrescribir un manifest existente.

## add

Conda es la fuente predeterminada y los flags seleccionan otro ecosistema. `--spec` establece la versión (por defecto `*`), mientras que `--env` apunta a un entorno con nombre.

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

Cada paquete declarado se verifica contra el ecosistema en el que fue declarado. Conda se verifica contra el entorno de pixi, npm contra `.chefe/node_modules` y cargo contra el `.crates.toml` del entorno. chefe reporta cada uno como `✓` ok, `≠` desviación o `✗` faltante, con un conteo transitivo.

## run y shell

```sh
chefe run build
chefe shell                # shell activada en el entorno predeterminado
chefe shell serving
```

## x

```sh
chefe x ruff check .                   # ejecuta una herramienta en un entorno desechable, no requiere manifest
chefe x --with build python -m build   # agrega paquetes extra con --with
```

Al igual que `uvx` o `pipx run`, `chefe x` aprovisiona un entorno efímero para la herramienta y la ejecuta, sin dejar ningún `chefe.toml` atrás.

## global install

```sh
chefe global install          # expone las [deps] de conda como un entorno global compartido
chefe global install mytools
```

## clean

```sh
chefe clean                   # borra .chefe/, una instalación nueva de chefe lo reconstruye
```