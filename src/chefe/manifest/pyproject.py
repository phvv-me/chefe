import tomllib
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import cast

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from .. import MANIFEST, NAME, PYPROJECT
from ..base import Toml

# PEP 735 lets one dependency group pull in another; chefe follows the reference so the whole
# transitive group reaches the dev environment.
INCLUDE_GROUP = "include-group"


def find_manifest(directory: Path) -> Path | None:
    """The chefe manifest for ``directory``.

    A `pyproject.toml` carrying `[tool.chefe]` wins, else a standalone `chefe.toml`, else `None`.
    Embedding the manifest in `pyproject.toml` mirrors how ruff, pytest, and hatch read their own
    `[tool.*]` tables, so a Python package keeps one file. A `pyproject.toml` with no chefe table
    (a monorepo root that drives chefe from a sibling `chefe.toml`) falls through to the standalone
    file, so that layout keeps working unchanged.
    """
    pyproject = directory / PYPROJECT
    if pyproject.is_file() and NAME in tool_table(pyproject):
        return pyproject
    manifest = directory / MANIFEST
    return manifest if manifest.is_file() else None


def tool_table(pyproject: Path) -> Mapping[str, Toml]:
    """The `[tool]` table of ``pyproject``, or an empty mapping when it declares none."""
    return _table(tomllib.loads(pyproject.read_text()).get("tool"))


class Sources:
    """The `[tool.chefe.sources]` routing table: how each distribution is satisfied.

    A `[project.dependencies]` or `[dependency-groups]` entry names a distribution and pins its
    version. A source entry keyed by that name redirects it to a provider, `conda` (with an
    optional `package` rename), `git`, or `path`, without repeating the version. The version and
    extras still come from the PEP 508 requirement, so routing never duplicates the constraint.
    """

    def __init__(self, table: Mapping[str, Toml]) -> None:
        self.table = {canonicalize_name(name): dict(spec) for name, spec in _tables(table)}

    def route(self, requirement: Requirement) -> tuple[bool, str, Toml]:
        """Route ``requirement`` to `(is_conda, name, spec)` for its pixi table.

        `is_conda` picks the conda `[dependencies]` table over the `[pypi-dependencies]` one. A
        conda route carries the version (extras have no conda meaning); a git or path route carries
        its source keys and the extras; a plain PyPI dep carries version and extras.
        """
        version = str(requirement.specifier) or None
        extras = sorted(requirement.extras)
        source = self.table.get(canonicalize_name(requirement.name))
        provider = str(source.get("provider", "pypi")) if source is not None else "pypi"
        if source is not None and provider == "conda":
            return True, str(source.get("package", requirement.name)), version or "*"
        if source is not None and provider != "pypi":
            keys = {key: value for key, value in source.items() if key != "provider"}
            return False, requirement.name, {**keys, **({"extras": extras} if extras else {})}
        return False, requirement.name, pypi_spec(version, extras)


def manifest_body(text: str) -> dict[str, Toml]:
    """The manifest a `pyproject.toml` carries under `[tool.chefe]`, with `[project]` folded in.

    Ownership stays split: `[project.dependencies]` owns publishable runtime deps and
    `[dependency-groups].dev` owns dev tools, both PEP-standard and inherited here so the built
    wheel and the chefe dev env never restate a version. `[tool.chefe.sources]` routes a named
    distribution to conda, git, or path; `[tool.chefe.conda]` adds conda-only natives with no PEP
    508 form; and the rest of `[tool.chefe]` (channels, tasks, env, overlays) passes through.
    """
    data = tomllib.loads(text)
    project = _table(data.get("project"))
    tool = _table(data.get("tool"))
    chefe = dict(_table(tool.get(NAME)))
    sources = Sources(_table(chefe.pop("sources", {})))
    conda_only = dict(_table(chefe.pop("conda", {})))
    body: dict[str, Toml] = chefe
    name_workspace(body, project)
    dependencies = cast(Iterable[str], project.get("dependencies", []))
    runtime_conda, runtime_pypi = route(dependencies, sources)
    project_name = project.get("name")
    self_install(runtime_pypi, project_name if isinstance(project_name, str) else None)
    fill_scope(body, {**conda_only, **runtime_conda}, runtime_pypi)
    groups = _table(data.get("dependency-groups"))
    dev_conda, dev_pypi = route(group(groups, "dev"), sources)
    fill_dev(body, dev_conda, dev_pypi)
    return body


def route(
    requirements: Iterable[str], sources: Sources
) -> tuple[dict[str, Toml], dict[str, Toml]]:
    """Split PEP 508 ``requirements`` into their conda and PyPI dep tables via ``sources``."""
    conda: dict[str, Toml] = {}
    pypi: dict[str, Toml] = {}
    for requirement in requirements:
        is_conda, name, spec = sources.route(Requirement(requirement))
        (conda if is_conda else pypi)[name] = spec
    return conda, pypi


def group(groups: Mapping[str, Toml], name: str, seen: set[str] | None = None) -> list[str]:
    """The PEP 735 dependency group ``name`` flattened, following `include-group` references."""
    seen = seen if seen is not None else set()
    entries = groups.get(name)
    if name in seen or not isinstance(entries, Iterable) or isinstance(entries, str):
        return []
    seen.add(name)
    flat: list[str] = []
    for entry in entries:
        if isinstance(entry, Mapping):
            flat.extend(group(groups, str(entry[INCLUDE_GROUP]), seen))
        else:
            flat.append(str(entry))
    return flat


def self_install(pypi: dict[str, Toml], name: str | None) -> None:
    """Install the package itself editable so it imports and its own deps resolve, `pip -e .`."""
    if name and not any(canonicalize_name(key) == canonicalize_name(name) for key in pypi):
        pypi[name] = {"path": ".", "editable": True}


def fill_scope(body: dict[str, Toml], conda: Mapping[str, Toml], pypi: Mapping[str, Toml]) -> None:
    """Write the root conda `[deps]` and Python deps, each only when it carries something."""
    if conda:
        body["deps"] = {**dict(_table(body.get("deps"))), **conda}
    fill_python(body, pypi)


def fill_dev(body: dict[str, Toml], conda: Mapping[str, Toml], pypi: Mapping[str, Toml]) -> None:
    """Write the `[dev]` feature's conda and Python deps, so dev tools install beside runtime."""
    dev = dict(_table(body.get("dev")))
    if conda:
        dev["deps"] = {**dict(_table(dev.get("deps"))), **conda}
    fill_python(dev, pypi)
    if dev:
        body["dev"] = dev


def fill_python(scope: dict[str, Toml], pypi: Mapping[str, Toml]) -> None:
    """Merge ``pypi`` into ``scope``'s Python toolchain deps, leaving any options table intact.

    The toolchain table is only written when it has deps, so a scope with none keeps a bare
    manifest and never trips the "declare `python` in `[deps]`" guard.
    """
    if not pypi:
        return
    python = dict(_table(scope.get("python")))
    python["deps"] = {**dict(_table(python.get("deps"))), **pypi}
    scope["python"] = python


def name_workspace(body: dict[str, Toml], project: Mapping[str, Toml]) -> None:
    """Fill the workspace identity from `[project]`, keeping any `[tool.chefe.workspace]` value."""
    workspace = dict(_table(body.get("workspace")))
    name = project.get("name")
    if name is not None:
        workspace.setdefault("name", name)
    if "version" in project:
        workspace.setdefault("version", project["version"])
    body["workspace"] = workspace


def pypi_spec(version: str | None, extras: list[str]) -> Toml:
    """A plain PyPI dep spec: a bare version string, or a table when it carries extras."""
    if extras:
        return {**({"version": version} if version else {}), "extras": extras}
    return version or "*"


def _table(value: Toml | None) -> Mapping[str, Toml]:
    """Return ``value`` when it is a TOML table, otherwise an empty mapping."""
    return value if isinstance(value, Mapping) else {}


def _tables(table: Mapping[str, Toml]) -> Iterable[tuple[str, Mapping[str, Toml]]]:
    """The ``(name, mapping)`` entries of a routing table, skipping any non-table value."""
    return ((name, spec) for name, spec in table.items() if isinstance(spec, Mapping))
