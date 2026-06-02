# O manifest

Tudo reside em um único `chefe.toml`. O cabeçalho configura o workspace, `[deps]` e as tabelas por ecossistema declaram pacotes, e sobreposições de plataforma e ambientes nomeados compõem o restante.

## Workspace

```toml
[workspace]
name     = "my-project"
platforms = ["osx-arm64", "linux-64"]
channels = ["conda-forge", "nvidia"]
dotenv   = true                 # lê o .env para o ambiente, ativado por padrão
```

## Dependências

A tabela `[deps]` simples é **conda**, a fonte padrão. Uma string simples é uma especificação de versão, e `*` significa qualquer uma.

```toml
[deps]
python = ">=3.11"
nodejs = ">=22"
ripgrep = "*"
pueue  = ">=4"
```

## PyPI

Pacotes PyPI são resolvidos pelo pixi-via-`uv` no **mesmo** ambiente. `[pypi]` contém configurações, `[pypi.deps]` os pacotes, e `[pypi.indexes]` índices extras nomeados.

```toml
[pypi]
index-strategy = "unsafe-best-match"

[pypi.indexes]
pytorch = "https://download.pytorch.org/whl/cu124"

[pypi.deps]
torch = { version = ">=2.6", index = "pytorch" }
ruff  = ">=0.6"
```

## Outros ecossistemas

Todo outro ecossistema é explícito, portanto nada é inferido.

```toml
[cargo.deps]
bookokrat = "*"

[npm.deps]
prettier = ">=3"
"@tobilu/qmd" = "*"
```

!!! tip "Runtimes são garantidos automaticamente"
    Cada ecossistema precisa de seu runtime de linguagem para instalar e executar, então o chefe o adiciona do conda-forge quando ausente. `[pypi.deps]` garante o `python`, `[npm.deps]` garante o `nodejs`, `[cargo.deps]` garante o `rust`, e `[gem.deps]` garante o `ruby`. Declare seu próprio `python` (ou outros) fixado em `[deps]` e o chefe não o alterará. Isso também se aplica por ambiente, então um ambiente `no-default` que usa `[pypi.deps]` ainda obtém seu próprio `python`.

## Requisitos de sistema

A base de pacotes virtuais do conda usada para resolução multiplataforma, não um carregamento de módulo.

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

## Sobreposições de plataforma

Adicione dependências condicionalmente por plataforma, e elas são compiladas para alvos nativos do pixi. Qualquer escopo é aninhado sob `[on.…]`.

```toml
[on.linux.deps]
cupy = ">=13"

[on.linux-aarch64.pypi.deps]
some-arm-wheel = "*"
```

## Ambientes nomeados

Componha ambientes extras, como recursos do pixi. `no-default = true` exclui as dependências base.

```toml
[envs.serving]
no-default = true

[envs.serving.pypi.deps]
vllm = ">=0.6"
```

Instale ou inspecione um com `chefe install serving` ou `chefe tree serving`.

## Tarefas

Comandos nomeados que são executados dentro do ambiente, acessados com `chefe run <task>`.

```toml
[tasks]
serve = { run = "python -m my_project.server", depends = ["build"] }
build = "python -m my_project.build"
```