from collections.abc import Mapping
from typing import cast

import tomlkit
from pydantic import Field

from ..base import Model, Toml
from ..manifest import Manifest, Spec, Task

# pixi tables whose values are dependency specs; a ``path`` *source* lives inside
# one of these specs, never at the dep-name level.
DEP_TABLES = ("dependencies", "pypi-dependencies")


def reroot_source(spec: Toml) -> Toml:
    """A single dep spec with a repo-relative local ``path`` source shifted up one level.

    The compiled manifest is emitted under ``.chefe/``, so ``packages/lote`` must
    resolve as ``../packages/lote`` — the same shift applied to task ``cwd`` and
    activation scripts. A bare version string, a table without ``path``, or an
    absolute ``path`` ride through untouched.
    """
    if isinstance(spec, dict) and isinstance(path := spec.get("path"), str) and path[:1] != "/":
        return {**spec, "path": f"../{path}"}
    return spec


def reparent(value: Toml) -> Toml:
    """Reroot local path deps in the compiled tables, leaving everything else as is.

    Only a ``path`` carried as a dependency *source* (a value under a
    ``dependencies`` / ``pypi-dependencies`` table) is shifted, so a dependency
    literally named ``path`` keeps its version untouched.
    """
    if isinstance(value, dict):
        return {
            key: {name: reroot_source(spec) for name, spec in item.items()}
            if key in DEP_TABLES and isinstance(item, dict)
            else reparent(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [reparent(item) for item in value]
    return value


class PixiManifest(Model):
    """The compiled pixi manifest (`pixi.toml`) emitted into the generated env."""

    workspace: dict[str, Toml]
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
        body = self.model_dump(by_alias=True, exclude_defaults=True)
        self.inline_platforms(body["workspace"])
        return tomlkit.dumps(body)

    @staticmethod
    def inline_platforms(table: dict[str, Toml]) -> None:
        """Render detailed platform descriptors as Pixi inline tables."""
        platforms = table.get("platforms")
        if not isinstance(platforms, list) or not any(
            isinstance(platform, dict) for platform in platforms
        ):
            return
        rendered = tomlkit.array()
        for platform in platforms:
            if isinstance(platform, str):
                rendered.append(platform)
                continue
            descriptor = tomlkit.inline_table()
            descriptor.update(cast(Mapping[str, Toml], platform))
            rendered.append(descriptor)
        table["platforms"] = rendered

    @staticmethod
    def task(spec: Task) -> Task:
        """Translate a mise-style task into pixi's (`run` -> `cmd`, `depends` -> `depends-on`).

        A task that runs a command runs it from the repo root, which is one directory up from the
        generated `.chefe/`, so repo-relative commands (`python -m pkg`) resolve as written, and a
        `dir` rebases that root. A command-less aggregator (only `depends`) carries no working
        directory: pixi rejects `cwd` without a `cmd`, and a directory means nothing with no
        command to run there, so the rebase is skipped for it.
        """
        out: dict[str, Toml] = {}
        if isinstance(spec, str):
            out["cmd"] = spec
        else:
            renamed = {"run": "cmd", "depends": "depends-on", "dir": "cwd"}
            out = {renamed.get(key, key): value for key, value in spec.items()}
        if "cmd" in out:
            cwd = str(out.get("cwd", ""))
            out["cwd"] = cwd if cwd.startswith("/") else f"../{cwd}" if cwd else ".."
        return out

    @staticmethod
    def platforms(names: list[str], system: dict[str, str], feature: str = "") -> list[Toml]:
        """Attach virtual-package floors to Pixi's platform descriptors.

        names: target platform names from the Chefe manifest.
        system: virtual-package versions such as the CUDA driver floor.
        feature: optional feature name used to create a distinct rich platform.
        """
        platforms: list[Toml] = []
        if system:
            platforms.extend(
                {
                    "name": f"{name}-{feature}" if feature else name,
                    "platform": name,
                    **system,
                }
                for name in names
            )
        else:
            platforms.extend(names)
        return platforms

    @classmethod
    def from_manifest(cls, m: Manifest) -> PixiManifest:
        """Build the pixi manifest from a validated :class:`Manifest`."""
        python = m.python()
        indexes = python.indexes
        variables = {k: v for k, v in m.env.items() if not k.startswith("_.")}
        # the manifest is emitted under `.chefe/`, so a repo-root script path
        # resolves one directory up from where pixi runs it; the generated dotenv
        # loader lives beside the manifest and runs first so user scripts see the vars
        scripts = [path if path.startswith("/") else f"../{path}" for path in m.activation.scripts]
        if m.workspace.dotenv:
            scripts.insert(0, "dotenv.sh")
        activation: dict[str, Toml] = {
            **({"env": variables} if variables else {}),
            **({"scripts": scripts} if scripts else {}),
        }
        workspace_platforms = cls.platforms(m.workspace.platforms, m.system, "system")
        root_platforms = (
            [f"{platform}-system" for platform in m.workspace.platforms]
            if m.system
            else m.workspace.platforms
        )
        feature: dict[str, Toml] = {}
        for name, env in m.envs.items():
            body = env.feature(indexes)
            if env.system:
                selected = env.platforms or m.workspace.platforms
                if env.system == m.system:
                    body["platforms"] = [f"{platform}-system" for platform in selected]
                else:
                    workspace_platforms.extend(cls.platforms(selected, env.system, name))
                    body["platforms"] = [f"{platform}-{name}" for platform in selected]
            elif env.platforms and m.system:
                body["platforms"] = [f"{platform}-system" for platform in env.platforms]
            feature[name] = body
        environments: dict[str, Toml] = {
            name: {
                "features": [name],
                **({"no-default-feature": True} if env.no_default else {}),
            }
            for name, env in m.envs.items()
        }
        default_features: list[str] = []
        if m.system:
            feature["chefe-system"] = {"platforms": root_platforms}
            default_features.append("chefe-system")
        # `[dev.*]` deps become a `dev` feature added to the default environment, so
        # `chefe install` provisions dev tooling beside the runtime deps.
        if dev := m.dev.tables(indexes):
            feature["dev"] = dev
            default_features.append("dev")
        if default_features:
            environments["default"] = {"features": default_features}
        workspace: dict[str, Toml] = {
            "name": m.workspace.name,
            "version": m.workspace.version,
            "channels": m.workspace.channels,
            "platforms": workspace_platforms,
        }
        payload: dict[str, Toml] = {
            "workspace": workspace,
            "activation": activation,
            **m.tables(indexes),
            "pypi-options": python.options(),
            "target": {plat: scope.tables(indexes) for plat, scope in m.on.items()},
            "feature": feature,
            "environments": environments,
            "tasks": {name: cls.task(spec) for name, spec in m.tasks.items()},
        }
        return cls.model_validate(reparent(payload))
