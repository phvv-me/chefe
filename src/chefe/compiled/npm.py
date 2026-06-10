from ..base import FlexModel, Toml
from ..errors import ChefeError
from ..manifest import Manifest, Spec
from ..utils import current_platform


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
    def from_manifest(
        cls, m: Manifest, env: str = "default", platform: str = ""
    ) -> PackageJson | None:
        """Build package.json from the `[nodejs]` toolchain merged for ``env`` on ``platform``.

        The merged view folds the base table with `[dev]`, platform overlays, and the named
        env, so a dep declared in any active scope reaches the compiled manifest.
        """
        nodejs = m.toolchains_for(env, platform or current_platform()).get("nodejs")
        if nodejs is None:
            return None
        deps = nodejs.deps
        dev = nodejs.dev.deps
        if not deps and not dev:
            return None
        name = m.workspace.name if nodejs.app else f"{m.workspace.name}-npm"
        fields: dict[str, Toml] = {
            "name": name,
            "dependencies": {pkg: cls.render(pkg, spec) for pkg, spec in deps.items()},
            **nodejs.package,
        }
        if dev:
            fields["devDependencies"] = {pkg: cls.render(pkg, s) for pkg, s in dev.items()}
        return cls.model_validate(fields)

    @staticmethod
    def render(name: str, spec: Spec) -> str:
        """The npm version string for ``spec``, refusing source forms npm would misread.

        A `path`/`git`/`url` spec silently compiled to `"*"` would install a registry package
        of the same name, so anything beyond a version fails fast instead.
        """
        extras = sorted(set(spec.model_extra or {}) | ({"index"} if spec.index else set()))
        if extras:
            raise ChefeError(
                f"[nodejs] dep `{name}` carries {', '.join(extras)}, which chefe cannot express "
                "in package.json. Pin a version here and put source overrides under "
                "[nodejs.package] instead."
            )
        return spec.version or "*"
