<div align="center">

[![chefe banner](https://raw.githubusercontent.com/phvv-me/chefe/main/docs/assets/banner.png)](https://phvv.me/chefe)

[![CI](https://github.com/phvv-me/chefe/actions/workflows/ci.yml/badge.svg)](https://github.com/phvv-me/chefe/actions/workflows/ci.yml)
[![Publish](https://github.com/phvv-me/chefe/actions/workflows/publish.yml/badge.svg)](https://github.com/phvv-me/chefe/actions/workflows/publish.yml)
[![PyPI](https://img.shields.io/pypi/v/chefe)](https://pypi.org/project/chefe/)
[![Python](https://img.shields.io/pypi/pyversions/chefe)](https://pypi.org/project/chefe/)
[![Docs](https://img.shields.io/badge/docs-phvv.me%2Fchefe-EAB308)](https://phvv.me/chefe)
[![Coverage](https://img.shields.io/badge/coverage-100%25-brightgreen)](https://github.com/phvv-me/chefe/actions/workflows/ci.yml)

</div>

> **Warning** chefe is early (`0.0.x`). The manifest and commands may still change.

## Installation

```sh
pip install chefe      # or: pipx install chefe
```

chefe installs [pixi](https://pixi.sh), the engine it compiles to, on first run, so a single
`pip install` is all you need.

## What it is

Conda, Python, Node.js, Rust, and whatever toolchains your project declares. Real projects need several at once, scattered across `pixi.toml`, `package.json`, and language-specific manifests. chefe is the head chef. You write **one `chefe.toml`** recipe, chefe runs the line and plates a single environment. It never re-implements a solver. It runs the cooks.

```toml
[workspace]
name     = "my-project"
channels = ["conda-forge"]

[deps]                      # bare table is conda, the default resolver
python  = ">=3.11"
nodejs  = ">=25"
rust    = "*"
ripgrep = "*"

[python.deps]               # table name matches the package in [deps]
torch = ">=2.6"

[nodejs.dev.deps]           # table name matches the package in [deps]
prettier = ">=3"

[rust.deps]
bookokrat = "*"
```

## Usage

```sh
chefe init                 # scaffold a chefe.toml
chefe add ripgrep          # conda is the default resolver
chefe add torch -l python
chefe add prettier -l nodejs
chefe install              # provision every language/toolchain at once
chefe x ruff check .       # run a tool in a throwaway env, like pipx run
chefe tree                 # what's declared vs installed, per language/toolchain
```

> **Tip** run `chefe tree` anytime to see declared vs installed across every language/toolchain at a glance.

## Lore

A head chef never cooks every dish alone. They write the recipe and run the line, and the cooks each work their station. `chefe` does the same for your dependencies.
