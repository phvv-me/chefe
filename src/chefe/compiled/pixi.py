from __future__ import annotations

import tomlkit
from pydantic import Field

from ..base import Model, Toml
from ..manifest import Manifest, Spec, Task


class PixiManifest(Model):
    """The compiled pixi manifest (`pixi.toml`) emitted into the generated env."""

    workspace: dict[str, Toml]
    system_requirements: dict[str, str] = Field(default_factory=dict, alias="system-requirements")
    activation: dict[str, Toml] = {}
    dependencies: dict[str, Spec] = {}
    pypi_dependencies: dict[str, Spec] = Field(default_factory=dict, alias="pypi-dependencies")
    pypi_options: dict[str, Toml] = Field(default_factory=dict, alias="pypi-options")
    target: dict[str, Toml] = {}
    feature: dict[str, Toml] = {}
    environments: dict[str, Toml] = {}
    tasks: dict[str, Task] = {}

    def to_toml(self) -> str:
        """Render to `pixi.toml` text (hyphenated table names via the field aliases)."""
        return tomlkit.dumps(self.model_dump(by_alias=True, exclude_defaults=True))

    @staticmethod
    def task(spec: Task) -> Task:
        """Translate a mise-style task into pixi's (`run` -> `cmd`, `depends` -> `depends-on`).

        Tasks run from the repo root, which is one directory up from the generated `.chefe/`,
        so repo-relative commands (`python -m pkg`, `node_modules/.bin/x`) resolve as written.
        """
        out: dict[str, Toml] = {}
        if isinstance(spec, str):
            out["cmd"] = spec
        else:
            renamed = {"run": "cmd", "depends": "depends-on", "dir": "cwd"}
            out = {renamed.get(key, key): value for key, value in spec.items()}
        out["cwd"] = f"../{out['cwd']}" if "cwd" in out else ".."
        return out

    @classmethod
    def from_manifest(cls, m: Manifest) -> PixiManifest:
        """Build the pixi manifest from a validated :class:`Manifest`."""
        indexes = m.pypi.indexes
        env = {k: v for k, v in m.env.items() if not k.startswith("_.")}
        # the manifest is emitted under `.chefe/`, so a repo-root script path
        # resolves one directory up from where pixi runs it
        scripts = [path if path.startswith("/") else f"../{path}" for path in m.activation.scripts]
        activation = {
            **({"env": env} if env else {}),
            **({"scripts": scripts} if scripts else {}),
        }
        return cls.model_validate(
            {
                "workspace": {
                    "name": m.workspace.name,
                    "version": m.workspace.version,
                    "channels": m.workspace.channels,
                    "platforms": m.workspace.platforms,
                },
                "system-requirements": m.system,
                "activation": activation,
                **m.tables(indexes),
                "pypi-options": m.pypi.options(),
                "target": {plat: scope.tables(indexes) for plat, scope in m.on.items()},
                "feature": {name: env.feature(indexes) for name, env in m.envs.items()},
                "environments": {
                    name: {
                        "features": [name],
                        **({"no-default-feature": True} if env.no_default else {}),
                    }
                    for name, env in m.envs.items()
                },
                "tasks": {name: cls.task(spec) for name, spec in m.tasks.items()},
            }
        )
