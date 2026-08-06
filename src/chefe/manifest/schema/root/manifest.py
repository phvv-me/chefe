import tomllib
from collections.abc import Mapping
from importlib.metadata import version
from pathlib import Path
from typing import Self

from pydantic import model_validator

from ....core import Declared, Project, Task, platform_scopes
from ...pyproject import manifest_body
from ..deps import Runtimes, ToolchainSpec
from ..scopes import Env, Scope
from ..workspace import Activation, Header, Modules


class Manifest(Scope):
    """The validated Chefe manifest."""

    workspace: Header
    system: dict[str, str] = {}
    on: dict[str, Scope] = {}
    dev: Scope = Scope()
    envs: dict[str, Env] = {}
    env: dict[str, str] = {}
    activation: Activation = Activation()
    modules: Modules = Modules()
    tasks: dict[str, Task] = {}

    @classmethod
    def from_pyproject(cls, text: str) -> Self:
        """Validate the Chefe table and inherited Python project metadata."""
        return cls.model_validate(manifest_body(text))

    @classmethod
    def from_toml(cls, text: str) -> Self:
        """Parse and validate a Chefe manifest string."""
        return cls.model_validate(tomllib.loads(text))

    @classmethod
    def load(cls, path: Path) -> Self:
        """Read and validate a Chefe or Python project manifest."""
        text = path.read_text()
        return cls.from_pyproject(text) if path.name == Project.pyproject else cls.from_toml(text)

    def active_scopes(self, env: str, *, platform: str) -> list[Scope]:
        """Return dependency scopes active for one environment and platform."""
        selectors = platform_scopes(platform)
        named = self.envs.get(env) if env != "default" else None
        scopes: list[Scope] = []
        if named is None or not named.no_default:
            scopes.extend([self, *(scope for key, scope in self.on.items() if key in selectors)])
        if named is not None:
            scopes.extend([named, *(scope for key, scope in named.on.items() if key in selectors)])
        return scopes

    def declared(self, env: str, *, platform: str) -> dict[str, Declared]:
        """Return every dependency declared for an environment and platform."""
        scopes = self.active_scopes(env, platform=platform)
        if env == "default":
            scopes.append(self.dev)
        groups = [group for scope in scopes for group in scope.groups().items()]
        return {
            name: Declared(source=source, spec=spec.version or "*")
            for source, dependencies in groups
            for name, spec in dependencies.items()
        }

    def local_python_projects(self) -> list[str]:
        """Return every declared local Python project path that contributes lock metadata."""
        scopes: list[Scope] = [self, self.dev, *self.on.values()]
        for environment in self.envs.values():
            scopes.extend([environment, *environment.on.values()])
        return sorted(
            {
                path
                for scope in scopes
                for spec in scope.groups().get("python", {}).values()
                if isinstance(path := (spec.model_extra or {}).get("path"), str)
            }
        )

    def python(self) -> ToolchainSpec:
        """Return root Python toolchain settings or an empty spec."""
        return self.toolchains().get("python", ToolchainSpec())

    @model_validator(mode="after")
    def reserved_env_names(self) -> Self:
        """Reject names owned by Chefe's generated Pixi features."""
        if reserved := {"chefe-platforms", "default", "dev"} & set(self.envs):
            names = ", ".join(f"[envs.{name}]" for name in sorted(reserved))
            raise ValueError(
                f"{names} is reserved. The base manifest is the default environment and "
                "Chefe owns its generated features, so use another env name."
            )
        return self

    @model_validator(mode="after")
    def toolchain_tables_must_be_declared(self) -> Self:
        """Reject runtime-keyed tables without a matching runtime dependency."""
        root = set(self.deps)
        scopes: list[tuple[str, Scope, set[str]]] = [
            ("", self, root),
            ("dev.", self.dev, root),
            *((f"on.{platform}.", scope, root) for platform, scope in self.on.items()),
        ]
        for name, environment in self.envs.items():
            local = root | set(environment.deps)
            scopes.append((f"envs.{name}.", environment, local))
            scopes.extend(
                (f"envs.{name}.on.{platform}.", scope, local)
                for platform, scope in environment.on.items()
            )
        missing = sorted(
            f"[{location}{table}]"
            for location, scope, allowed in scopes
            for table, spec in (scope.model_extra or {}).items()
            if isinstance(spec, Mapping)
            and table not in allowed | set(scope.deps)
            and not Runtimes.providers(table) & allowed
        )
        if missing:
            raise ValueError(
                f"{', '.join(missing)} has no matching package in [deps]. This is often a table "
                f"from a newer {Project.name} than the {version(Project.name)} you have, so try "
                f"`pip install -U {Project.name}`, otherwise add it to [deps] or remove it."
            )
        return self

    def toolchains_for(self, env: str, *, platform: str) -> dict[str, ToolchainSpec]:
        """Merge toolchain specs from every active scope."""
        scopes = self.active_scopes(env, platform=platform)
        if env == "default":
            scopes.append(self.dev)
        merged: dict[str, ToolchainSpec] = {}
        for scope in scopes:
            for name, spec in scope.toolchains().items():
                merged[name] = merged[name].merge(spec) if name in merged else spec
        return merged
