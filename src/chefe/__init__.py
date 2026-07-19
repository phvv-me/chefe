# The package name *is* the project name (the build maps pyproject -> this package),
# so a rename is a single move of the `src/chefe` folder. Everything naming derives
# from it; reading pyproject.toml at runtime would be fragile (it isn't in the wheel).
NAME = __name__

# The manifest a user writes, and the env directory generated beside it.
MANIFEST = f"{NAME}.toml"
ENV_DIR = f".{NAME}"

# A Python package may embed the manifest as a `[tool.chefe]` table here instead of a
# standalone `chefe.toml`, the same way ruff, pytest, and hatch read their own `[tool.*]`.
PYPROJECT = "pyproject.toml"

# Pixi resolves conda directly; Python packages use Pixi's private Python adapter.
PIXI_RESOLVED = ("conda", "python")

# `chefe global add -l <lang>` aliases: the runtime name a user types, and the ecosystem name
# of the backend it routes to. Both the runtime (`nodejs`) and the ecosystem (`npm`) resolve here.
GLOBAL_LANGUAGES = {
    "conda": "conda",
    "python": "pypi",
    "pypi": "pypi",
    "pip": "pypi",
    "nodejs": "npm",
    "npm": "npm",
    "rust": "cargo",
    "cargo": "cargo",
}

# The conda runtime package each non-conda ecosystem needs in the global env: pip/npm/cargo run
# from inside the env, so adding a pypi/npm/cargo package to a fresh env first installs this
# runtime so the env owns the matching toolchain (`chefe global add codex -l nodejs` just works).
GLOBAL_RUNTIMES = {"pypi": "python", "npm": "nodejs", "cargo": "rust"}
