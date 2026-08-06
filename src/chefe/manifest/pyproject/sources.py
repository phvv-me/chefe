from collections.abc import Mapping

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from ...core import Toml


class Sources:
    """The `[tool.chefe.sources]` routing table: how each distribution is satisfied.

    A `[project.dependencies]` or `[dependency-groups]` entry names a distribution and pins its
    version. A source entry keyed by that name redirects it to a provider, `conda` (with an
    optional `package` rename), `git`, or `path`, without repeating the version. The version and
    extras still come from the PEP 508 requirement, so routing never duplicates the constraint.
    """

    def __init__(self, table: Mapping[str, Toml]) -> None:
        self.table = {
            canonicalize_name(name): dict(spec)
            for name, spec in table.items()
            if isinstance(spec, Mapping)
        }

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
        if extras:
            spec = {**({"version": version} if version else {}), "extras": extras}
            return False, requirement.name, spec
        return False, requirement.name, version or "*"
