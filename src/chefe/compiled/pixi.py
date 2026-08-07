from collections.abc import Sequence

import tomlkit
from pydantic import Field

from ..core import Model, Task, Toml
from ..manifest import Env, Manifest, Spec
from .platforms import PlatformMatrix

# pixi tables whose values are dependency specs; a ``path`` *source* lives inside
# one of these specs, never at the dep-name level.
_DEP_TABLES = ("dependencies", "pypi-dependencies")

_PLATFORMS = "platforms"


def _reroot_source(spec: Toml) -> Toml:
    """A single dep spec with a repo-relative local ``path`` source shifted up one level.

    The compiled manifest is emitted under ``.chefe/``, so ``packages/lote`` must
    resolve as ``../packages/lote`` — the same shift applied to task ``cwd`` and
    activation scripts. A bare version string, a table without ``path``, or an
    absolute ``path`` ride through untouched.
    """
    if isinstance(spec, dict) and isinstance(path := spec.get("path"), str) and path[:1] != "/":
        return {**spec, "path": f"../{path}"}
    return spec


def _reparent(value: Toml) -> Toml:
    """Reroot local path deps in the compiled tables, leaving everything else as is.

    Only a ``path`` carried as a dependency *source* (a value under a
    ``dependencies`` / ``pypi-dependencies`` table) is shifted, so a dependency
    literally named ``path`` keeps its version untouched.
    """
    if isinstance(value, dict):
        return {
            key: {name: _reroot_source(spec) for name, spec in item.items()}
            if key in _DEP_TABLES and isinstance(item, dict)
            else _reparent(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_reparent(item) for item in value]
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

    @staticmethod
    def activation_table(m: Manifest) -> dict[str, Toml]:
        """The `[activation]` table: exported env vars plus the scripts pixi sources on entry.

        The manifest is emitted under `.chefe/`, so a repo-root script path resolves one
        directory up from where pixi runs it. The generated dotenv loader lives beside the
        manifest and is sourced first, so a user script already sees the vars it loaded.
        """
        variables = {k: v for k, v in m.env.items() if not k.startswith("_.")}
        scripts = [path if path.startswith("/") else f"../{path}" for path in m.activation.scripts]
        if m.workspace.dotenv:
            scripts.insert(0, "dotenv.sh")
        return {
            **({"env": variables} if variables else {}),
            **({"scripts": scripts} if scripts else {}),
        }

    @staticmethod
    def platform_array(platforms: Sequence[Toml]) -> tomlkit.items.Array:
        """The workspace platform list as tomlkit items, each named variant an inline table."""
        rendered = tomlkit.array()
        for platform in platforms:
            if isinstance(platform, dict):
                descriptor = tomlkit.inline_table()
                descriptor.update(platform)
                rendered.append(descriptor)
            else:
                rendered.append(platform)
        return rendered

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

    @classmethod
    def declared_feature(
        cls, name: str, env: Env, platforms: PlatformMatrix, indexes: dict[str, str]
    ) -> Toml:
        """One `[feature.<name>]` table: the env's own deps, plus its platforms and tasks."""
        return {
            **env.feature(indexes),
            **(
                {_PLATFORMS: platforms.environments[name]}
                if name in platforms.environments
                else {}
            ),
            **(
                {"tasks": {task: cls.task(spec) for task, spec in env.tasks.items()}}
                if env.tasks
                else {}
            ),
        }

    @classmethod
    def features(
        cls, m: Manifest, platforms: PlatformMatrix, indexes: dict[str, str]
    ) -> tuple[dict[str, Toml], dict[str, Toml]]:
        """The `[feature]` and `[environments]` tables: one feature per declared env, plus chefe's.

        Beyond the declared envs, chefe owns two synthetic features that the default environment
        picks up: `chefe-platforms` carries the workspace platform matrix, and `dev` carries the
        `[dev.*]` deps so `chefe install` provisions dev tooling beside the runtime deps.
        """
        feature: dict[str, Toml] = {
            name: cls.declared_feature(name, env, platforms, indexes)
            for name, env in m.envs.items()
        }
        environments: dict[str, Toml] = {
            name: {
                "features": [name],
                **({"no-default-feature": True} if env.no_default else {}),
            }
            for name, env in m.envs.items()
        }
        owned: dict[str, Toml] = {
            **({"chefe-platforms": {_PLATFORMS: platforms.default}} if platforms.default else {}),
            **({"dev": dev} if (dev := m.dev.tables(indexes)) else {}),
        }
        feature.update(owned)
        if owned:
            environments["default"] = {"features": list(owned)}
        return feature, environments

    @classmethod
    def from_manifest(cls, m: Manifest) -> PixiManifest:
        """Build the pixi manifest from a validated :class:`Manifest`."""
        python = m.python()
        indexes = python.indexes
        platforms = PlatformMatrix.from_manifest(m)
        feature, environments = cls.features(m, platforms, indexes)
        payload: dict[str, Toml] = {
            "workspace": {
                "name": m.workspace.name,
                "version": m.workspace.version,
                "channels": m.workspace.channels,
                _PLATFORMS: platforms.workspace,
            },
            "activation": cls.activation_table(m),
            **m.tables(indexes),
            "pypi-options": python.options(),
            "target": {plat: scope.tables(indexes) for plat, scope in m.on.items()},
            "feature": feature,
            "environments": environments,
            "tasks": {name: cls.task(spec) for name, spec in m.tasks.items()},
        }
        return cls.model_validate(_reparent(payload))

    def to_toml(self) -> str:
        """Render to `pixi.toml` text (hyphenated table names via the field aliases)."""
        body = self.model_dump(by_alias=True, exclude_defaults=True)
        body["workspace"][_PLATFORMS] = self.platform_array(body["workspace"][_PLATFORMS])
        return tomlkit.dumps(body)
