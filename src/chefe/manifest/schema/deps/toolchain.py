from typing import Self

from ....core import FlexModel, Toml
from .registry import Registry
from .runtimes import Runtimes
from .spec import Spec


class ToolchainSpec(FlexModel):
    """One runtime-keyed toolchain table."""

    manager: str | None = None
    deps: dict[str, Spec] = {}
    dev: Registry = Registry()
    app: bool = False
    package: dict[str, Toml] = {}
    bin_dirs: list[str] = []
    indexes: dict[str, str] = {}

    def all_deps(self) -> dict[str, Spec]:
        """Merge runtime and development dependency maps."""
        return {**self.deps, **self.dev.deps}

    def manager_package(self) -> str | None:
        """Return the package needed to provision a standalone manager."""
        return self.manager if Runtimes.provisions(self.manager) else None

    def merge(self, other: Self) -> Self:
        """Overlay another toolchain while preserving both package maps."""
        return self.model_copy(
            update={
                "manager": other.manager or self.manager,
                "deps": {**self.deps, **other.deps},
                "dev": Registry(deps={**self.dev.deps, **other.dev.deps}),
                "app": self.app or other.app,
                "package": {**self.package, **other.package},
                "bin_dirs": [*self.bin_dirs, *other.bin_dirs],
                "indexes": {**self.indexes, **other.indexes},
            }
        )

    def options(self) -> dict[str, Toml]:
        """Return extra nondependency settings carried by the toolchain."""
        return dict(self.model_extra or {})
