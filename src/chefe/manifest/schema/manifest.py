import tomllib
from collections.abc import Mapping
from importlib.metadata import version
from pathlib import Path
from typing import Self

from pydantic import model_validator

from ... import NAME, PYPROJECT
from ...state import Declared
from ...utils import platform_scopes
from ..pyproject import manifest_body
from .activation import Activation
from .environment import Env
from .header import Header
from .modules import Modules
from .scope import Scope
from .toolchain import ToolchainSpec
from .typings import Task


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
        root = frozenset(self.deps)
        scopes: list[tuple[str, Scope, frozenset[str]]] = [
            ("", self, root),
            ("dev.", self.dev, root),
            *((f"on.{platform}.", scope, root) for platform, scope in self.on.items()),
        ]
        for name, environment in self.envs.items():
            local = root | frozenset(environment.deps)
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
            and table not in allowed | frozenset(scope.deps)
            and not ToolchainSpec.RUNTIME_PACKAGES.get(table, frozenset()) & allowed
        )
        if missing:
            raise ValueError(
                f"{', '.join(missing)} has no matching package in [deps]. This is often a table "
                f"from a newer {NAME} than the {version(NAME)} you have, so try "
                f"`pip install -U {NAME}`, otherwise add it to [deps] or remove it."
            )
        return self

    @classmethod
    def load(cls, path: Path) -> Self:
        """Read and validate a Chefe or Python project manifest."""
        text = path.read_text()
        return cls.from_pyproject(text) if path.name == PYPROJECT else cls.from_toml(text)

    @classmethod
    def from_pyproject(cls, text: str) -> Self:
        """Validate the Chefe table and inherited Python project metadata."""
        return cls.model_validate(manifest_body(text))

    @classmethod
    def from_toml(cls, text: str) -> Self:
        """Parse and validate a Chefe manifest string."""
        return cls.model_validate(tomllib.loads(text))

    def active_scopes(self, env: str, platform: str) -> list[Scope]:
        """Return dependency scopes active for one environment and platform."""
        selectors = platform_scopes(platform)
        named = self.envs.get(env) if env != "default" else None
        scopes: list[Scope] = []
        if named is None or not named.no_default:
            scopes.extend([self, *(scope for key, scope in self.on.items() if key in selectors)])
        if named is not None:
            scopes.extend([named, *(scope for key, scope in named.on.items() if key in selectors)])
        return scopes

    def declared(self, env: str, platform: str) -> dict[str, Declared]:
        """Return every dependency declared for an environment and platform."""
        scopes = self.active_scopes(env, platform)
        if env == "default":
            scopes.append(self.dev)
        return {
            name: Declared(source=source, spec=spec.version or "*")
            for scope in scopes
            for source, dependencies in scope.groups().items()
            for name, spec in dependencies.items()
        }

    def python(self) -> ToolchainSpec:
        """Return root Python toolchain settings or an empty spec."""
        return self.toolchains().get("python", ToolchainSpec())

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

    def toolchains_for(self, env: str, platform: str) -> dict[str, ToolchainSpec]:
        """Merge toolchain specs from every active scope."""
        scopes = self.active_scopes(env, platform)
        if env == "default":
            scopes.append(self.dev)
        merged: dict[str, ToolchainSpec] = {}
        for scope in scopes:
            for name, spec in scope.toolchains().items():
                merged[name] = merged[name].merge(spec) if name in merged else spec
        return merged
