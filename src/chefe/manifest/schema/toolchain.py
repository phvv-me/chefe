from typing import ClassVar, Self

from ...base import FlexModel, Toml
from .registry import Registry
from .spec import Spec


class ToolchainSpec(FlexModel):
    """One runtime-keyed toolchain table."""

    PROVISIONABLE_MANAGERS: ClassVar[frozenset[str]] = frozenset({"pnpm", "yarn", "bun", "uv"})
    RUNTIME_PACKAGES: ClassVar[dict[str, frozenset[str]]] = {
        "python": frozenset({"python", "python-freethreading"}),
    }

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
        return self.manager if self.manager in self.PROVISIONABLE_MANAGERS else None

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
