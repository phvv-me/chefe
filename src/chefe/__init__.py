from __future__ import annotations

# The package name *is* the project name (the build maps pyproject -> this package),
# so a rename is a single move of the `src/chefe` folder. Everything naming derives
# from it; reading pyproject.toml at runtime would be fragile (it isn't in the wheel).
NAME = __name__

# The manifest a user writes, and the env directory generated beside it.
MANIFEST = f"{NAME}.toml"
ENV_DIR = f".{NAME}"

# Domain constants: the non-conda ecosystems, and the sources pixi resolves itself.
ECOSYSTEMS = ("pypi", "cargo", "npm", "gem")
PIXI_RESOLVED = ("conda", "pypi")
