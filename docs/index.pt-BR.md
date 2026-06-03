# chefe

Um manifest para cada gerenciador de pacotes.

Conda, PyPI, npm, cargo. Projetos reais precisam de vários ao mesmo tempo, espalhados por `pixi.toml`, `package.json` e `Cargo.toml`. O **chefe** é o chef de cozinha: você escreve **uma única receita `chefe.toml`**, ele compila cada manifest nativo dentro de `.chefe/`, executa as ferramentas reais e serve tudo como um único ambiente. Ele nunca reimplementa um solver. Ele comanda os cozinheiros.

<div class="grid cards" markdown>

- :material-silverware-variant: **Uma receita**

    Cada ecossistema em um único `chefe.toml`. Chega de fazer malabarismo com quatro manifests.

- :material-cog-transfer-outline: **Saída nativa**

    Compila para `pixi.toml`, `package.json` e companhia, de verdade. As ferramentas de fato é que resolvem.

- :material-source-branch: **Combinável**

    Sobreposições por plataforma e ambientes nomeados se empilham como features do pixi.

- :material-broom: **Autocontido**

    Todo o ambiente vive em `.chefe/`, então um único comando apaga tudo.

</div>

## Instalação

```sh
pip install chefe      # or: uv tool install chefe
```

o chefe instala o [pixi](https://pixi.sh), o motor para o qual ele compila, na primeira execução, então um único `pip install` é tudo de que você precisa.

```toml title="chefe.toml"
[workspace]
name = "my-project"

[deps]                 # conda, the default source
python  = ">=3.12"
ripgrep = "*"

[pypi.deps]
torch = ">=2.6"

[npm.deps]
prettier = ">=3"
```

!!! warning "chefe ainda é inicial (`0.0.x`)"
    O formato do manifest e os comandos ainda podem mudar.

## A seguir

<div class="grid cards" markdown>

- [:material-cogs: **Como funciona**](how-it-works.md) — o pipeline de compilar e executar.
- [:material-console: **Comandos**](commands.md) — a CLI completa.
- [:material-file-document-outline: **Manifest**](manifest.md) — cada tabela do `chefe.toml`.
- [:material-test-tube: **Exemplos**](examples.md) — uma receita de monorepo do mundo real.

</div>

## Lore

Um chef de cozinha nunca prepara cada prato sozinho. Ele escreve a receita e comanda a linha, e cada cozinheiro trabalha na sua estação. Os gerenciadores de pacotes espalhados são essa linha, então o chefe os dirige a partir de uma única receita. 🧑‍🍳
