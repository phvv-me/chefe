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

A tabela `[deps]` pura é **conda**, a fonte padrão. Uma string simples é uma especificação de versão, e `*` significa qualquer uma.

```toml
[deps]
python = ">=3.11"
nodejs = ">=22"
ripgrep = "*"
pueue  = ">=4"
```

## PyPI

Os pacotes PyPI são resolvidos pelo pixi via `uv` no **mesmo** ambiente. `[pypi]` guarda as configurações, `[pypi.deps]` os pacotes e `[pypi.indexes]` índices extras nomeados.

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

!!! tip "Os runtimes são garantidos automaticamente"
    Cada ecossistema precisa do runtime da sua linguagem para instalar e executar, então o chefe
    o adiciona do conda-forge quando ele falta. `[pypi.deps]` garante o `python`, `[npm.deps]` garante o `nodejs`,
    `[cargo.deps]` garante o `rust` e `[gem.deps]` garante o `ruby`. Declare seu próprio
    `python` (ou outros) fixado em `[deps]` e o chefe o deixa em paz. Isso também vale por ambiente,
    então um ambiente `no-default` que usa `[pypi.deps]` ainda recebe seu próprio `python`.

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
[on.linux.deps]
cupy = ">=13"

[on.linux-aarch64.pypi.deps]
some-arm-wheel = "*"
```

## Ambientes nomeados

Combine ambientes extras, como features do pixi. `no-default = true` exclui as dependências base, e `platforms` restringe o ambiente a onde ele pode ser construído (assim um ambiente de GPU é pulado ao resolver em um laptop).

```toml
[envs.serving]
no-default = true
platforms  = ["linux-64", "linux-aarch64"]

[envs.serving.pypi.deps]
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
