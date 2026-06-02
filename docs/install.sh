#!/bin/sh
# chefe installer. Ensures pixi (the engine chefe compiles to) and uv, then installs chefe.
# Run with  curl -fsSL https://phvv.me/chefe/install.sh | sh
set -eu

say() { printf '\033[33mchefe\033[0m %s\n' "$1"; }

if ! command -v pixi >/dev/null 2>&1; then
  say "installing pixi"
  curl -fsSL https://pixi.sh/install.sh | sh
fi

if ! command -v uv >/dev/null 2>&1; then
  say "installing uv"
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi

say "installing chefe"
uv tool install --upgrade chefe

say "done, run 'chefe init' to start"
