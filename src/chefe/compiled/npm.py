from __future__ import annotations

from ..base import FlexModel, Toml
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
        """Build package.json from the npm deps (runtime + dev), or None when there are none.

        An application (``[npm] app``) takes the workspace name and merges ``[npm.package]``;
        tooling keeps the ``-npm`` suffix so a generated env file never shadows a real package.
        ``[dev.npm.deps]`` becomes ``devDependencies``, emitted only when present so a manifest
        without dev deps compiles to the exact same file as before.
        """
        if not m.npm.deps and not m.dev.npm.deps:
            return None
        name = m.workspace.name if m.npm.app else f"{m.workspace.name}-npm"
        dependencies = {package: spec.version or "*" for package, spec in m.npm.deps.items()}
        fields: dict[str, Toml] = {"name": name, "dependencies": dependencies, **m.npm.package}
        if m.dev.npm.deps:
            fields["devDependencies"] = {
                pkg: s.version or "*" for pkg, s in m.dev.npm.deps.items()
            }
        return cls.model_validate(fields)
