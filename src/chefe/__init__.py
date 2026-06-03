# The package name *is* the project name (the build maps pyproject -> this package),
# so a rename is a single move of the `src/chefe` folder. Everything naming derives
# from it; reading pyproject.toml at runtime would be fragile (it isn't in the wheel).
NAME = __name__

# The manifest a user writes, and the env directory generated beside it.
MANIFEST = f"{NAME}.toml"
ENV_DIR = f".{NAME}"

# Pixi resolves conda directly; Python packages use Pixi's private Python adapter.
PIXI_RESOLVED = ("conda", "python")
