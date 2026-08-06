import tomllib
from collections.abc import Mapping
from pathlib import Path

from ...core import Project, Toml


def find_manifest(directory: Path) -> Path | None:
    """The chefe manifest for ``directory``.

    A `pyproject.toml` carrying `[tool.chefe]` wins, else a standalone `chefe.toml`, else `None`.
    Embedding the manifest in `pyproject.toml` mirrors how ruff, pytest, and hatch read their own
    `[tool.*]` tables, so a Python package keeps one file. A `pyproject.toml` with no chefe table
    (a monorepo root that drives chefe from a sibling `chefe.toml`) falls through to the standalone
    file, so that layout keeps working unchanged.
    """
    pyproject = directory / Project.pyproject
    if pyproject.is_file() and Project.name in tool_table(pyproject):
        return pyproject
    manifest = directory / Project.manifest
    return manifest if manifest.is_file() else None


def tool_table(pyproject: Path) -> Mapping[str, Toml]:
    """The `[tool]` table of ``pyproject``, or an empty mapping when it declares none."""
    table = tomllib.loads(pyproject.read_text()).get("tool")
    return table if isinstance(table, Mapping) else {}
