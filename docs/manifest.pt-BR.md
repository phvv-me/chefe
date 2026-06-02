# O manifest

Tudo vive em um único `chefe.toml`. O cabeçalho configura o workspace, `[deps]` e as tabelas por ecossistema declaram pacotes, e sobreposições por plataforma e ambientes nomeados se combinam por cima.

## Workspace

```toml
[workspace]
name     = "my-project"
platforms = ["osx-arm64", "linux-64"]
channels = ["conda-forge", "nvidia"]
dotenv   = true                 # read .env into the environment, on by default
```

## Dependências

A tabela `[deps]` pura é **conda**, a fonte padrão. Uma string simples é uma especificação de versão, e `*` significa qualquer uma.

```toml
[deps]
python = ">=3.11"
nodejs = ">=22"
ripgrep = "*"
pueue  = ">=4"
```

## PyPI

Pacotes PyPI são resolvidos pelo pixi-via-`uv` no **mesmo** ambiente. `[pypi]` guarda as configurações, `[pypi.deps]` os pacotes e `[pypi.indexes]` índices extras nomeados.

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

Todo outro ecossistema é explícito, então nada é inferido.

```toml
[cargo.deps]
bookokrat = "*"

[npm.deps]
prettier = ">=3"
"@tobilu/qmd" = "*"
```

!!! tip "Runtimes são garantidos automaticamente"
    Cada ecossistema precisa do seu runtime de linguagem para instalar e executar, então o chefe o adiciona a partir do
    conda-forge quando ausente. `[pypi.deps]` garante `python`, `[npm.deps]` garante `nodejs`,
    `[cargo.deps]` garante `rust` e `[gem.deps]` garante `ruby`. Declare seu próprio
    `python` fixado (ou outros) em `[deps]` e o chefe o deixa intacto. Isso vale por ambiente também,
    então um ambiente `no-default` que usa `[pypi.deps]` ainda recebe seu próprio `python`.

## Requisitos de sistema

O piso de pacotes virtuais do conda usado na resolução multiplataforma, e não um carregamento de módulo.

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

## Sobreposições por plataforma

Adicione deps condicionalmente por plataforma, e elas compilam para targets nativos do pixi. Qualquer escopo se aninha sob `[on.…]`.

```toml
[on.linux.deps]
cupy = ">=13"

[on.linux-aarch64.pypi.deps]
some-arm-wheel = "*"
```

## Ambientes nomeados

Componha ambientes extras, como features do pixi. `no-default = true` exclui as deps base.

```toml
[envs.serving]
no-default = true

[envs.serving.pypi.deps]
vllm = ">=0.6"
```

Instale ou inspecione um com `chefe install serving` ou `chefe tree serving`.

## Tasks

Comandos nomeados que executam dentro do ambiente, acessados com `chefe run <task>`.

```toml
[tasks]
serve = { run = "python -m my_project.server", depends = ["build"] }
build = "python -m my_project.build"
```
