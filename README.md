<div align="center">

<img src="docs/assets/logo.svg" width="148" alt="chefe logo, a domed serving cloche" />

# chefe

**One manifest for every package manager.** 🧑‍🍳

[![CI](https://github.com/phvv-me/chefe/actions/workflows/ci.yml/badge.svg)](https://github.com/phvv-me/chefe/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/chefe.svg?color=EAB308)](https://pypi.org/project/chefe/)
[![Docs](https://img.shields.io/badge/docs-phvv.me%2Fchefe-EAB308)](https://phvv.me/chefe)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

</div>

> [!WARNING]
> **chefe is early (`0.0.x`).** The manifest and commands may still change.

## Installation

```sh
curl -fsSL https://phvv.me/chefe/install.sh | sh
```

This installs [pixi](https://pixi.sh) (the engine chefe compiles to) and chefe itself. Prefer the raw package? Use `pip install chefe` or `uv tool install chefe`.

## What it is

Conda, PyPI, npm, cargo. Real projects need several at once, scattered across `pixi.toml`, `package.json`, and `Cargo.toml`. chefe is the head chef. You write **one `chefe.toml`** recipe, chefe runs the line (pixi, npm, cargo) and plates a single environment. It never re-implements a solver. It runs the cooks.

```toml
[workspace]
name     = "my-project"
channels = ["conda-forge"]

[deps]                      # bare table is conda, the default source
python  = ">=3.11"
ripgrep = "*"

[pypi.deps]                 # resolved by pixi-via-uv, in the same env
torch = ">=2.6"

[cargo.deps]                # other ecosystems are explicit via [<eco>.deps]
bookokrat = "*"

[npm.deps]
prettier = ">=3"
```

## Usage

```sh
chefe init                 # scaffold a chefe.toml
chefe add ripgrep          # add deps, use --pypi / --cargo / --npm for others
chefe install              # provision every ecosystem at once
chefe tree                 # what's declared vs installed, per ecosystem
```

> [!TIP]
> Run `chefe tree` anytime to see declared vs installed across every ecosystem at a glance. ✅

> [!NOTE]
> Full documentation lives at **[phvv.me/chefe](https://phvv.me/chefe)**.

## Lore

A head chef never cooks every dish alone. They write the recipe and run the line, and the cooks each work their station. chefe does the same for your dependencies. One recipe in, one plated environment out, with pixi, npm, and cargo working the stations. 🧑‍🍳
