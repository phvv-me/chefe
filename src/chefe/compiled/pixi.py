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
        so repo-relative commands (`python -m pkg`) resolve as written.
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
        python = m.python()
        indexes = python.indexes
        variables = {k: v for k, v in m.env.items() if not k.startswith("_.")}
        # the manifest is emitted under `.chefe/`, so a repo-root script path
        # resolves one directory up from where pixi runs it
        scripts = [path if path.startswith("/") else f"../{path}" for path in m.activation.scripts]
        activation = {
            **({"env": variables} if variables else {}),
            **({"scripts": scripts} if scripts else {}),
        }
        feature: dict[str, Toml] = {name: env.feature(indexes) for name, env in m.envs.items()}
        environments: dict[str, Toml] = {
            name: {
                "features": [name],
                **({"no-default-feature": True} if env.no_default else {}),
            }
            for name, env in m.envs.items()
        }
        # `[dev.*]` deps become a `dev` feature added to the default environment, so
        # `chefe install` provisions dev tooling beside the runtime deps.
        if dev := cls.dev_feature(m, indexes):
            feature["dev"] = dev
            environments["default"] = {"features": ["dev"]}
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
                "pypi-options": python.options(),
                "target": {plat: scope.tables(indexes) for plat, scope in m.on.items()},
                "feature": feature,
                "environments": environments,
                "tasks": {name: cls.task(spec) for name, spec in m.tasks.items()},
            }
        )

    @staticmethod
    def dev_feature(m: Manifest, indexes: dict[str, str]) -> dict[str, Toml]:
        """The `[dev.*]` conda + Python deps as a pixi feature."""
        deps = dict(m.dev.deps)
        python = m.dev.toolchains().get("python")
        feature: dict[str, Toml] = {}
        if deps:
            feature["dependencies"] = {name: spec.to_toml() for name, spec in deps.items()}
        if python and python.all_deps():
            feature["pypi-dependencies"] = {
                name: spec.with_index(indexes).to_toml()
                for name, spec in python.all_deps().items()
            }
        return feature
