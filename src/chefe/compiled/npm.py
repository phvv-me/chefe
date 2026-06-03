from __future__ import annotations

from ..base import FlexModel, Toml
from ..manifest import Manifest


class PackageJson(FlexModel):
    """The compiled `package.json` emitted for the Node.js toolchain.

    Extra keys ride through from `[nodejs.package]` (e.g. `type`, `engines`, `pnpm`), so an
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
        """Build package.json from `[nodejs]` deps, or None when there are none."""
        nodejs = m.toolchains().get("nodejs")
        if nodejs is None:
            return None
        deps = nodejs.deps
        dev = nodejs.dev.deps
        if not deps and not dev:
            return None
        name = m.workspace.name if nodejs.app else f"{m.workspace.name}-npm"
        dependencies = {package: spec.version or "*" for package, spec in deps.items()}
        fields: dict[str, Toml] = {"name": name, "dependencies": dependencies, **nodejs.package}
        if dev:
            fields["devDependencies"] = {pkg: s.version or "*" for pkg, s in dev.items()}
        return cls.model_validate(fields)
