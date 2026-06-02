from __future__ import annotations

from ..base import Model
from ..manifest import Manifest


class PackageJson(Model):
    """The compiled `package.json` emitted into the generated env."""

    name: str
    private: bool = True
    dependencies: dict[str, str] = {}

    def to_json(self) -> str:
        """Render to `package.json` text."""
        return self.model_dump_json(indent=2) + "\n"

    @classmethod
    def from_manifest(cls, m: Manifest) -> PackageJson | None:
        """Build package.json from ``[npm.deps]``, or None if there are none."""
        if not m.npm.deps:
            return None
        return cls(
            name=f"{m.workspace.name}-npm",
            dependencies={package: spec.version or "*" for package, spec in m.npm.deps.items()},
        )
