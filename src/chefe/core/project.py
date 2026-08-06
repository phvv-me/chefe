class Project:
    """Every name Chefe answers to, derived once from the package name.

    The package name *is* the project name, since the build maps pyproject onto this package, so
    a rename is a single move of the `src/chefe` folder. Reading pyproject.toml at runtime would
    be fragile instead, because the file is not in the wheel. `manifest` is what a user writes
    and `env_dir` is the generated directory beside it, while `pyproject` is the alternative
    home for a `[tool.chefe]` table, the way ruff, pytest, and hatch read their own `[tool.*]`.
    `pixi_resolved` names the two sources pixi resolves itself, conda directly and Python
    through its private adapter.
    """

    name = __name__.split(".")[0]
    manifest = f"{name}.toml"
    env_dir = f".{name}"
    pyproject = "pyproject.toml"
    pixi_resolved = ("conda", "python")
