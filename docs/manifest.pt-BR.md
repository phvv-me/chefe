# O manifest

Tudo vive em um único `chefe.toml`. O cabeçalho configura o workspace, `[deps]` e as tabelas por ecossistema declaram pacotes, e as sobreposições por plataforma e os ambientes nomeados se combinam por cima.

## Workspace

```toml
[workspace]
name     = "my-project"
platforms = ["osx-arm64", "linux-64"]
channels = ["conda-forge", "nvidia"]
dotenv   = true                 # read .env into the environment, on by default
```

## Dependências

A tabela `[deps]` pura é **conda**, o resolvedor padrão. Uma string simples é uma especificação de versão, e `*` significa qualquer uma.

```toml
[deps]
python = ">=3.11"
nodejs = ">=22"
ripgrep = "*"
pueue  = ">=4"
```

## Python

Os pacotes Python são resolvidos pelo pixi no **mesmo** ambiente. `[python]` guarda as configurações, `[python.deps]` os pacotes e `[python.indexes]` índices extras nomeados.

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

Todo outro ecossistema é explícito, então nada é inferido.

```toml
[rust.deps]
bookokrat = "*"

[nodejs.dev.deps]
prettier = ">=3"
"@tobilu/qmd" = "*"
```

!!! tip "Os runtimes são garantidos automaticamente"
    Cada ecossistema precisa do runtime da sua linguagem para instalar e executar, então o chefe
    o adiciona do conda-forge quando ele falta. `[python.deps]` garante o `python`.
    Toolchains como `nodejs` e `rust` devem ser declaradas em `[deps]`. Declare seu próprio
    `python` (ou outros) fixado em `[deps]` e o chefe o deixa em paz. Isso também vale por ambiente,
    então um ambiente `no-default` que usa `[python.deps]` ainda recebe seu próprio `python`.

## Escolher o gerenciador do npm

O ecossistema Node.js usa o registro npm, e `manager` dentro de `[nodejs]` nomeia o binário que o
instala. O `package.json` compilado é o mesmo qualquer que seja a escolha do projeto, e o chefe
executa a ferramenta nomeada dentro do ambiente gerado, então funciona qualquer gerenciador de
pacotes que instale no seu diretório de trabalho, inclusive um que o chefe nunca tenha conhecido.

```toml
[nodejs]
manager = "pnpm"   # npm por padrão; pnpm, yarn ou qualquer binário compatível

[nodejs.deps]
svelte = ">=5"
```

`npm` é o padrão, então uma tabela `[nodejs.deps]` instala com npm quando `manager` não é definido. Nomear outra
ferramenta muda só o binário que o chefe executa, nunca as dependências, o registro ou o arquivo.

!!! note "O gerenciador precisa estar no PATH"
    Declare `nodejs` em `[deps]`; o binário do gerenciador é você quem fornece. Se o `manager`
    nomear uma ferramenta ausente, o comando real falha quando for executado.

## Aplicações JavaScript

Por padrão `[nodejs.deps]` é instalado como ferramentas dentro de `.chefe/`, ao lado do ambiente conda.
Uma aplicação define `app = true`, e o chefe instala na raiz do projeto e escreve ali um
`package.json` completo, para que Vite, SvelteKit e os demais resolvam `node_modules` do jeito usual.

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

`[nodejs.package]` é mesclado no `package.json` tal como está, então qualquer campo que uma ferramenta
espere passa sem alterações, de `type` e `engines` até os ajustes próprios de um gerenciador como o
`onlyBuiltDependencies` do pnpm. O chefe escreve o arquivo, então o `chefe.toml` continua sendo a
única coisa que você edita e um `package.json` gerado é um artefato de build que pode ir para o
gitignore.

## Dependências de desenvolvimento

`[dev.*]` espelha o scope base para ferramentas de que você precisa para construir e testar, mas não
para executar. Cada grupo compila para o mecanismo de desenvolvimento próprio do seu ecossistema, e
o `chefe install` as provisiona por padrão.

```toml
[dev.deps]            # ferramentas de desenvolvimento conda
ruff = "*"

[dev.python.deps]       # ferramentas de desenvolvimento Python
pytest = ">=8"

[nodejs.dev.deps]     # -> devDependencies do package.json
vite = ">=8"
```

`[nodejs.dev.deps]` vai para `devDependencies`, enquanto `[dev.deps]` e `[dev.python.deps]` viram uma
feature `dev` adicionada ao ambiente padrão, então seus linters e seu executor de testes são
instalados ao lado das dependências de execução. Isso é mais leve que um `[envs.dev]` completo, que é
um ambiente separado com a sua própria resolução.

## Requisitos de sistema

O piso de pacotes virtuais do conda usado para a resolução multiplataforma, não um carregamento de módulo.

```toml
[system]
cuda = "13.0"
```

## Variáveis de ambiente

Variáveis estáticas aplicadas quando o ambiente é ativado. O `.env` também é lido por padrão, alternado com `dotenv` no cabeçalho.

```toml
[env]
LOG_LEVEL = "info"
CUDA_MODULE_LOADING = "LAZY"
```

## Scripts de ativação

Scripts de shell carregados quando o ambiente é ativado, para configurações que variáveis de ambiente estáticas não conseguem expressar (caminhos computados, symlinks de bibliotecas). Eles compilam para os `[activation] scripts` do pixi; um caminho relativo à raiz do repositório continua funcionando a partir do `.chefe/` gerado.

```toml
[activation]
scripts = ["scripts/activate.sh"]
```

## Sobreposições por plataforma

Adicione dependências condicionalmente por plataforma, e elas compilam para os targets nativos do pixi. Qualquer escopo aninha sob `[on.…]`.

```toml

python = "*"

[on.linux-aarch64.python.deps]
some-arm-wheel = "*"
```

## Ambientes nomeados

Combine ambientes extras, como features do pixi. `no-default = true` exclui as dependências base, e `platforms` restringe o ambiente a onde ele pode ser construído (assim um ambiente de GPU é pulado ao resolver em um laptop).

```toml

python = "*"

[envs.serving.python.deps]
vllm = ">=0.6"
```

Instale ou inspecione um com `chefe install serving` ou `chefe tree serving`.

## Tasks

Comandos nomeados que rodam dentro do ambiente, alcançados com `chefe run <task>`. Eles executam *código*, nunca instalam dependências. Todo pacote pertence ao `[<eco>.deps]` do seu ecossistema, para que o `chefe install` e o `chefe global` cuidem dele. Uma task que recorre a `npm install -g` ou `cargo install` é o anti-padrão que o chefe substitui.

```toml
[tasks]
serve = { run = "python -m my_project.server", depends = ["build"] }
build = "python -m my_project.build"
```
