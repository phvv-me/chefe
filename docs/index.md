# chefe

One manifest for every package manager.

Conda, PyPI, npm, cargo. Real projects need several at once, scattered across `pixi.toml`, `package.json`, and `Cargo.toml`. **chefe** is the head chef: you write **one `chefe.toml`** recipe, it compiles each native manifest under `.chefe/`, runs the real tools, and plates them as a single environment. It never re-implements a solver. It runs the cooks.

<div class="grid cards" markdown>

- :material-silverware-variant: **One recipe**

    Every ecosystem in a single `chefe.toml`. No more juggling four manifests.

- :material-cog-transfer-outline: **Native output**

    Compiles to real `pixi.toml`, `package.json` and friends. The actual tools do the solving.

- :material-source-branch: **Composable**

    Platform overlays and named environments stack like pixi features.

- :material-broom: **Self-contained**

    The whole environment lives in `.chefe/`, so one command wipes it.

</div>

## Installation

```sh
pip install chefe      # or: uv tool install chefe
```

chefe installs [pixi](https://pixi.sh), the engine it compiles to, on first run, so a single `pip install` is all you need.

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

!!! warning "chefe is early (`0.0.x`)"
    The manifest format and commands may still change.

## Next

<div class="grid cards" markdown>

- [:material-cogs: **How it works**](how-it-works.md) — the compile-and-run pipeline.
- [:material-console: **Commands**](commands.md) — the full CLI.
- [:material-file-document-outline: **Manifest**](manifest.md) — every `chefe.toml` table.
- [:material-test-tube: **Examples**](examples.md) — a real-world monorepo recipe.

</div>

## Lore

A head chef never cooks every dish alone. They write the recipe and run the line, and the cooks each work their station. Scattered package managers are that line, so chefe directs them from one recipe. 🧑‍🍳
