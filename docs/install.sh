#!/bin/sh
# chefe installer. Installs pixi (the engine chefe compiles to) and chefe itself.
# Needs only curl — no uv, no pre-existing Python — so it works on a freshly
# built machine. Run with:  curl -fsSL https://phvv.me/chefe/install.sh | sh
set -eu

say() { printf '\033[33mchefe\033[0m %s\n' "$1"; }

# pixi is chefe's engine, and the Python chefe is installed with.
if ! command -v pixi >/dev/null 2>&1; then
  say "installing pixi"
  curl -fsSL https://pixi.sh/install.sh | sh
fi
PIXI_BIN="${PIXI_HOME:-$HOME/.pixi}/bin"
export PATH="$PIXI_BIN:$HOME/.local/bin:$PATH"

# chefe is a Python CLI. Build an isolated venv with pixi's own Python and pip
# chefe into it — pixi is the only dependency.
say "installing chefe"
pixi global install "python>=3.11" >/dev/null
CHEFE_HOME="${XDG_DATA_HOME:-$HOME/.local/share}/chefe"
"$PIXI_BIN/python" -m venv "$CHEFE_HOME"
"$CHEFE_HOME/bin/pip" install --quiet --upgrade pip chefe
mkdir -p "$HOME/.local/bin"
ln -sf "$CHEFE_HOME/bin/chefe" "$HOME/.local/bin/chefe"

say "done — ensure ~/.local/bin is on your PATH, then run 'chefe init'"
