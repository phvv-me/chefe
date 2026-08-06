import tomllib
from collections.abc import Iterable, Mapping, MutableMapping
from typing import cast

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from ...core import Project, Toml
from .sources import Sources

# PEP 735 lets one dependency group pull in another; chefe follows the reference so the whole
# transitive group reaches the dev environment.
_INCLUDE_GROUP = "include-group"


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
    chefe = dict(_table(_table(data.get("tool")).get(Project.name)))
    sources = Sources(_table(chefe.pop("sources", {})))
    conda_only = dict(_table(chefe.pop("conda", {})))
    body: dict[str, Toml] = chefe
    _name_workspace(body, project)
    _fold_runtime(body, project, sources, conda_only)
    _fold_dev(body, _table(data.get("dependency-groups")), sources)
    return body


def _route(
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
            flat.extend(group(groups, str(entry[_INCLUDE_GROUP]), seen))
        else:
            flat.append(str(entry))
    return flat


def _fold_runtime(
    body: dict[str, Toml],
    project: Mapping[str, Toml],
    sources: Sources,
    conda_only: Mapping[str, Toml],
) -> None:
    """Fold `[project.dependencies]` into the root scope, with the package itself installed too.

    The package goes in editable (`pip -e .`) so it imports and its own deps resolve, unless it
    already declares itself. `[tool.chefe.conda]` natives join the routed conda deps, since
    neither of them has a PEP 508 form `[project]` could have carried.
    """
    conda, pypi = _route(cast(Iterable[str], project.get("dependencies", [])), sources)
    name = project.get("name")
    if (
        isinstance(name, str)
        and name
        and not any(canonicalize_name(key) == canonicalize_name(name) for key in pypi)
    ):
        pypi[name] = {"path": ".", "editable": True}
    if merged := {**conda_only, **conda}:
        body["deps"] = {**dict(_table(body.get("deps"))), **merged}
    _fill_python(body, pypi)


def _fold_dev(body: dict[str, Toml], groups: Mapping[str, Toml], sources: Sources) -> None:
    """Fold the PEP 735 `dev` group into `[dev]`, so dev tools install beside the runtime deps."""
    conda, pypi = _route(group(groups, "dev"), sources)
    dev = dict(_table(body.get("dev")))
    if conda:
        dev["deps"] = {**dict(_table(dev.get("deps"))), **conda}
    _fill_python(dev, pypi)
    if dev:
        body["dev"] = dev


def _fill_python(scope: MutableMapping[str, Toml], pypi: Mapping[str, Toml]) -> None:
    """Merge ``pypi`` into ``scope``'s Python toolchain deps, leaving any options table intact.

    The toolchain table is only written when it has deps, so a scope with none keeps a bare
    manifest and never trips the "declare `python` in `[deps]`" guard.
    """
    if not pypi:
        return
    python = dict(_table(scope.get("python")))
    python["deps"] = {**dict(_table(python.get("deps"))), **pypi}
    scope["python"] = python


def _name_workspace(body: MutableMapping[str, Toml], project: Mapping[str, Toml]) -> None:
    """Fill the workspace identity from `[project]`, keeping any `[tool.chefe.workspace]` value."""
    workspace = dict(_table(body.get("workspace")))
    name = project.get("name")
    if name is not None:
        workspace.setdefault("name", name)
    if "version" in project:
        workspace.setdefault("version", project["version"])
    body["workspace"] = workspace


def _table(value: Toml | None) -> Mapping[str, Toml]:
    """Return ``value`` when it is a TOML table, otherwise an empty mapping."""
    return value if isinstance(value, Mapping) else {}
