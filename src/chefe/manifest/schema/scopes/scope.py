from collections.abc import Mapping

from pydantic import ConfigDict

from ....core import Model, Toml
from ..deps import Spec, ToolchainSpec


class Scope(Model):
    """Dependency groups shared by manifests, overlays, and environments."""

    model_config = ConfigDict(extra="allow", frozen=True, populate_by_name=True)

    deps: dict[str, Spec] = {}

    def groups(self) -> dict[str, dict[str, Spec]]:
        """Return every dependency group by source name."""
        return {
            "conda": self.deps,
            **{name: spec.all_deps() for name, spec in self.toolchains().items()},
        }

    def tables(self, indexes: dict[str, str]) -> dict[str, Toml]:
        """Compile this scope into Pixi dependency tables."""
        dependencies: dict[str, Toml] = {name: spec.to_toml() for name, spec in self.deps.items()}
        for toolchain in self.toolchains().values():
            if (package := toolchain.manager_package()) and package not in dependencies:
                dependencies[package] = "*"
        tables: dict[str, Toml] = {"dependencies": dependencies} if dependencies else {}
        if (python := self.toolchains().get("python")) and python.all_deps():
            tables["pypi-dependencies"] = {
                name: spec.with_index(indexes).to_toml()
                for name, spec in python.all_deps().items()
            }
        return tables

    def toolchains(self) -> dict[str, ToolchainSpec]:
        """Return runtime-keyed toolchain tables carried by this scope."""
        return {
            name: ToolchainSpec.model_validate(spec)
            for name, spec in (self.model_extra or {}).items()
            if isinstance(spec, Mapping)
        }
