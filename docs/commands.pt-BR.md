# Comandos

O chefe espelha os verbos do pixi sobre o manifest unificado. A maioria dos comandos aceita um `env` opcional, que assume `default` como padrão.

| comando | o que faz |
|---|---|
| `chefe init` | cria a estrutura de um `chefe.toml` inicial no diretório atual |
| `chefe sync` | compila o `chefe.toml` em `.chefe/{pixi.toml, package.json, …}` |
| `chefe install [env]` | sincroniza e então provisiona todo ecossistema para `env` |
| `chefe update [env]` | re-resolve para as versões permitidas mais recentes em todos os ecossistemas |
| `chefe add <pkg…>` | adiciona pacotes ao manifest e então re-sincroniza |
| `chefe remove <pkg…>` | remove pacotes onde quer que estejam declarados e então re-sincroniza |
| `chefe tree [env]` | declarado vs instalado, cada dep verificada em **seu próprio** ecossistema |
| `chefe run <task> [args…]` | executa uma task dentro do ambiente |
| `chefe x <cmd…>` | executa um comando em um ambiente descartável, como uvx ou pipx run |
| `chefe shell [env]` | abre um shell ativado em `env` |
| `chefe global install [name]` | instala as deps conda no ambiente pixi global compartilhado |
| `chefe clean` | remove o ambiente `.chefe/` gerado e os manifests |

## init

```sh
chefe init                 # name taken from the current directory
chefe init --name myproj
```

Escreve um `chefe.toml` mínimo com a plataforma atual, `conda-forge` e `python >=3.11`. Ele se recusa a sobrescrever um manifest existente.

## add

O conda é a fonte padrão, e as flags escolhem outro ecossistema. `--spec` define a versão (padrão `*`), enquanto `--env` mira um ambiente nomeado.

```sh
chefe add ripgrep numpy
chefe add torch --pypi --spec ">=2.6"
chefe add prettier --npm
chefe add vllm --pypi --env serving
```

As edições preservam seus comentários e formatação.

## tree

```sh
chefe tree
chefe tree serving
```

Cada pacote declarado é verificado no ecossistema em que foi declarado. O conda é checado no ambiente pixi, o npm em `.chefe/node_modules` e o cargo no `.crates.toml` do ambiente. O chefe marca cada um como `✓` ok, `≠` divergência ou `✗` ausente, com uma contagem transitiva.

## run e shell

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

Como o `uvx` ou o `pipx run`, o `chefe x` provisiona um ambiente efêmero para a ferramenta e a executa, sem deixar nenhum `chefe.toml` para trás.

## global install

```sh
chefe global install          # exposes the conda [deps] as a shared global env
chefe global install mytools
```

## clean

```sh
chefe clean                   # wipe .chefe/, a fresh chefe install rebuilds it
```
