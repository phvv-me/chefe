from __future__ import annotations

from ..base import FlexModel
from ..manifest import Manifest


class PackageJson(FlexModel):
    """The compiled `package.json` emitted for the npm ecosystem.

    Extra keys ride through from `[npm.package]` (e.g. `type`, `engines`, `pnpm`), so an
    application controls its own manifest fields without chefe hardcoding any framework.
    """

    name: str
    private: bool = True
    dependencies: dict[str, str] = {}

    def to_json(self) -> str:
        """Render to `package.json` text."""
        return self.model_dump_json(indent=2) + "\n"

    @classmethod
    def from_manifest(cls, m: Manifest) -> PackageJson | None:
        """Build package.json from ``[npm.deps]``, or None if there are none.

        An application (``[npm] app``) takes the workspace name and merges ``[npm.package]``;
        tooling keeps the ``-npm`` suffix so a generated env file never shadows a real package.
        """
        if not m.npm.deps:
            return None
        name = m.workspace.name if m.npm.app else f"{m.workspace.name}-npm"
        dependencies = {package: spec.version or "*" for package, spec in m.npm.deps.items()}
        return cls(name=name, dependencies=dependencies, **m.npm.package)
