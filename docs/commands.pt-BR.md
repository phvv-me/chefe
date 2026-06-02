# Comandos

O chefe espelha os verbos do pixi sobre o manifest unificado. A maioria dos comandos aceita um `env` opcional que tem como padrão `default`.

| comando | o que faz |
|---|---|
| `chefe init` | cria um `chefe.toml` inicial no diretório atual |
| `chefe sync` | compila o `chefe.toml` em `.chefe/{pixi.toml, package.json, …}` |
| `chefe install [env]` | sincroniza e, em seguida, provisiona cada ecossistema para o `env` |
| `chefe update [env]` | resolve novamente para as versões permitidas mais recentes em todos os ecossistemas |
| `chefe add <pkg…>` | adiciona pacotes ao manifest e, em seguida, ressincroniza |
| `chefe remove <pkg…>` | remove pacotes onde quer que estejam declarados e, em seguida, ressincroniza |
| `chefe tree [env]` | declarado vs instalado, cada dependência verificada em **seu próprio** ecossistema |
| `chefe run <task> [args…]` | executa uma tarefa dentro do ambiente |
| `chefe x <cmd…>` | executa um comando em um ambiente descartável, como uvx ou pipx run |
| `chefe shell [env]` | abre um shell ativado no `env` |
| `chefe global install [name]` | instala as dependências conda no ambiente pixi global compartilhado |
| `chefe clean` | remove o ambiente `.chefe/` gerado e os manifests |

## init

```sh
chefe init                 # nome retirado do diretório atual
chefe init --name myproj
```

Escreve um `chefe.toml` mínimo com a plataforma atual, `conda-forge` e `python >=3.11`. Ele se recusa a sobrescrever um manifest existente.

## add

O Conda é a fonte padrão, e as flags selecionam outro ecossistema. `--spec` define a versão (padrão `*`), enquanto `--env` aponta para um ambiente nomeado.

```sh
chefe add ripgrep numpy
chefe add torch --pypi --spec ">=2.6"
chefe add prettier --npm
chefe add vllm --pypi --env serving
```

As edições mantêm seus comentários e formatação.

## tree

```sh
chefe tree
chefe tree serving
```

Cada pacote declarado é verificado em relação ao ecossistema no qual foi declarado. O Conda é verificado contra o ambiente pixi, o npm contra `.chefe/node_modules` e o cargo contra o `.crates.toml` do ambiente. O chefe relata cada um como `✓` ok, `≠` divergente ou `✗` ausente, com uma contagem transitiva.

## run e shell

```sh
chefe run build
chefe shell                # shell ativado no ambiente padrão
chefe shell serving
```

## x

```sh
chefe x ruff check .                   # executa uma ferramenta em um ambiente descartável, sem necessidade de manifest
chefe x --with build python -m build   # adiciona pacotes extras com --with
```

Assim como o `uvx` ou `pipx run`, o `chefe x` provisiona um ambiente efêmero para a ferramenta e a executa, sem deixar nenhum `chefe.toml` para trás.

## global install

```sh
chefe global install          # expõe as [deps] do conda como um ambiente global compartilhado
chefe global install mytools
```

## clean

```sh
chefe clean                   # limpa o .chefe/, uma nova instalação do chefe o reconstrói
```