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
        if dev := m.dev.tables(indexes):
            feature["dev"] = dev
            environments["default"] = {"features": ["dev"]}
        workspace: dict[str, Toml] = {
            "name": m.workspace.name,
            "version": m.workspace.version,
            "channels": m.workspace.channels,
            "platforms": m.workspace.platforms,
        }
        payload: dict[str, Toml] = {
            "workspace": workspace,
            "system-requirements": m.system,
            "activation": activation,
            **m.tables(indexes),
            "pypi-options": python.options(),
            "target": {plat: scope.tables(indexes) for plat, scope in m.on.items()},
            "feature": feature,
            "environments": environments,
            "tasks": {name: cls.task(spec) for name, spec in m.tasks.items()},
        }
        return cls.model_validate(reparent(payload))
