# Comandos

chefe refleja los verbos de pixi sobre el manifest unificado. La mayoría de los comandos toman un `env` opcional que por defecto es `default`.

| comando | qué hace |
|---|---|
| `chefe init` | scaffold de un `chefe.toml` inicial en el directorio actual |
| `chefe sync` | compila `chefe.toml` en `.chefe/{pixi.toml, package.json, …}` |
| `chefe install [env]` | sync y luego aprovisiona cada ecosistema para `env` |
| `chefe update [env]` | vuelve a resolver a las versiones más nuevas permitidas en todos los lenguajes/toolchains |
| `chefe upgrade [pkg…]` | sube las restricciones de conda + Python del manifest a lo más reciente, luego sync |
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

Conda es el resolver por defecto, y `--language`/`-l` elige Python o cualquier runtime declarado en `[deps]`. `--spec` define la versión (por defecto `*`), mientras que `--env` apunta a un entorno con nombre.

```sh
chefe add ripgrep numpy
chefe add torch -l python --spec ">=2.6"
chefe add prettier -l nodejs
chefe add vllm -l python --env serving
```

Las ediciones conservan tus comentarios y formato.

## tree

```sh
chefe tree
chefe tree serving
```

Cada paquete declarado se verifica contra la fuente en la que fue declarado. Conda va contra el entorno de pixi, los paquetes Node.js contra `.chefe/node_modules`, y los crates Rust contra el `.crates.toml` del entorno. chefe reporta cada uno como `✓` ok, `≠` desviación, o `✗` faltante, con un conteo transitivo.

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

Aprovisiona cada fuente en un solo entorno global compartido, el equivalente de `chefe install` para herramientas que quieres en todas partes. Conda pasa por `pixi global`; los adaptadores luego usan binarios de ese entorno global para fuentes que necesitan una segunda etapa, como Python, Node.js y Rust.

```sh
chefe global install          # every language/toolchain's deps into a shared global env
chefe global install mytools  # name the env explicitly
```

## clean

```sh
chefe clean                   # wipe .chefe/, a fresh chefe install rebuilds it
```
