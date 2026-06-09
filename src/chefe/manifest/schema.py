from __future__ import annotations

import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Self

from pydantic import ConfigDict, Field, model_serializer, model_validator

from ..base import FlexModel, Model, Toml
from ..state import Declared

# A pixi/mise task: a bare command string, or a table (run/cmd, depends, cwd, ...).
Task = str | dict[str, Toml]


class Spec(FlexModel):
    """A dependency spec: a bare version string, or an inline table carrying a source.

    `version` and `index` are the keys we read (index resolves against `[python.indexes]`); any
    other source key (git / url / path / branch / build / channel / ...) rides through as a
    `FlexModel` extra to pixi/uv, which own their validation. Both forms render back to the
    simplest shape, so the manifest reads exactly as written.
    """

    version: str | None = None
    index: str | None = None

    @model_validator(mode="before")
    @classmethod
    def from_string(cls, data: Toml) -> Toml:
        """Accept a bare `"x"` spec as `{version: "x"}`."""
        return {"version": data} if isinstance(data, str) else data

    @model_serializer
    def to_toml(self) -> str | dict[str, Toml]:
        """Render to a string when it is only a version, else to an inline table."""
        extra = self.model_extra or {}
        if self.index is None and not extra:
            return self.version or "*"
        named = {
            key: value
            for key, value in (("version", self.version), ("index", self.index))
            if value
        }
        return {**named, **extra}

    def with_index(self, indexes: dict[str, str]) -> Spec:
        """This spec with a named `index` swapped for its URL from `[python.indexes]`."""
        if self.index in indexes:
            return self.model_copy(update={"index": indexes[self.index]})
        return self


class Registry(Model):
    """A dependency registry table: one ``deps`` map."""

    deps: dict[str, Spec] = {}


class ToolchainSpec(FlexModel):
    """A runtime-keyed toolchain table, discovered from `[deps]` package names.

    `manager`: executable used by this toolchain.
    `deps`: runtime dependencies managed by the toolchain.
    `dev`: development-only dependencies managed by the toolchain.
    """

    manager: str | None = None
    deps: dict[str, Spec] = {}
    dev: Registry = Registry()
    app: bool = False
    package: dict[str, Toml] = {}
    bin_dirs: list[str] = []
    indexes: dict[str, str] = {}

    def all_deps(self) -> dict[str, Spec]:
        """Runtime and dev dependency maps merged for installation and inspection."""
        return {**self.deps, **self.dev.deps}

    def options(self) -> dict[str, Toml]:
        """The extra non-dependency settings carried by this toolchain table."""
        return {key: value for key, value in (self.model_extra or {}).items()}

    def merge(self, other: ToolchainSpec) -> ToolchainSpec:
        """Overlay ``other`` onto this spec, preserving package maps from both scopes."""
        return self.model_copy(
            update={
                "manager": other.manager or self.manager,
                "deps": {**self.deps, **other.deps},
                "dev": Registry(deps={**self.dev.deps, **other.dev.deps}),
                "app": self.app or other.app,
                "package": {**self.package, **other.package},
                "bin_dirs": [*self.bin_dirs, *other.bin_dirs],
                "indexes": {**self.indexes, **other.indexes},
            }
        )


class Scope(Model):
    """A set of per-registry deps, shared by the base manifest, each platform overlay,
    and each environment. `deps` is conda, the default resolver."""

    model_config = ConfigDict(extra="allow", frozen=True, populate_by_name=True)

    deps: dict[str, Spec] = {}

    @model_validator(mode="after")
    def toolchain_tables_must_be_declared(self) -> Self:
        """Reject runtime-keyed tables without a matching package in `[deps]`."""
        missing = [
            name
            for name, spec in (self.model_extra or {}).items()
            if isinstance(spec, Mapping) and name not in self.deps
        ]
        if missing:
            names = ", ".join(f"[{name}]" for name in sorted(missing))
            raise ValueError(f"{names} must have matching entries in [deps]")
        return self

    def toolchains(self) -> dict[str, ToolchainSpec]:
        """Runtime-keyed toolchain tables whose names are declared in `[deps]`."""
        extras = self.model_extra or {}
        return {
            name: ToolchainSpec.model_validate(spec)
            for name, spec in extras.items()
            if name in self.deps and isinstance(spec, Mapping)
        }

    def groups(self) -> dict[str, dict[str, Spec]]:
        """Every dep group by source name: conda plus each runtime-keyed toolchain."""
        return {
            "conda": self.deps,
            **{name: spec.all_deps() for name, spec in self.toolchains().items()},
        }

    def tables(self, indexes: dict[str, str]) -> dict[str, Toml]:
        """This scope as pixi tables: conda deps plus Python packages.

        Each spec renders to its TOML form (a version string or an inline table), so the
        result is a plain nested `Toml` that pixi validates back into `Spec` on its own fields.
        """
        deps = dict(self.deps)
        out: dict[str, Toml] = {}
        if deps:
            out["dependencies"] = {name: spec.to_toml() for name, spec in deps.items()}
        if python := self.toolchains().get("python"):
            out["pypi-dependencies"] = {
                name: spec.with_index(indexes).to_toml()
                for name, spec in python.all_deps().items()
            }
        return out


class Env(Scope):
    """A named environment (→ pixi feature + environment); may carry its own overlays."""

    on: dict[str, Scope] = {}
    no_default: bool = Field(default=False, alias="no-default")
    platforms: list[str] = []  # restrict this env's feature to these platforms
    system: dict[str, str] = {}  # per-env system-requirements (virtual-package floor)

    def feature(self, indexes: dict[str, str]) -> dict[str, Toml]:
        """This env as a pixi feature: its registries, platform + system limits, and overlays."""
        body: dict[str, Toml] = {}
        body.update(self.tables(indexes))
        if self.platforms:
            body["platforms"] = self.platforms
        if self.system:
            body["system-requirements"] = self.system
        target: dict[str, Toml] = {}
        for plat, scope in self.on.items():
            if tables := scope.tables(indexes):
                target[plat] = tables
        if target:
            body["target"] = target
        return body


class Header(Model):
    """The ``[workspace]`` table: identity + solve surface."""

    name: str
    version: str = "0.1.0"
    platforms: list[str] = []
    channels: list[str] = ["conda-forge"]
    dotenv: bool = True


class Activation(Model):
    """Scripts sourced when the environment activates → pixi ``[activation] scripts``."""

    scripts: list[str] = []


class Modules(Model):
    """The ``[modules]`` table: HPC environment modules as ``name = "version"`` pairs.

    Each pair renders to one ``module load name/version`` spec, in declared order -- e.g.
    ``cuda = "13.2"`` and ``gcc = "15.2.0"`` become ``module load cuda/13.2 gcc/15.2.0`` in the
    generated `activate.sh`. On a host without Lmod/environment-modules (a laptop, gold) the
    load is guarded by ``command -v module`` and is a harmless no-op, so the same manifest is
    safe everywhere.
    """

    model_config = ConfigDict(extra="allow", frozen=True, populate_by_name=True)

    def specs(self) -> list[str]:
        """``name/version`` module specs in declared order (empty when no modules are set)."""
        return [f"{name}/{version}" for name, version in (self.model_extra or {}).items()]


class Manifest(Scope):
    """The whole manifest: a :class:`Scope` plus identity, conditions, env, tasks."""

    workspace: Header
    system: dict[str, str] = {}  # [system]  → pixi [system-requirements]
    on: dict[str, Scope] = {}  # [on.<platform>]  → pixi [target.*]
    # [dev.*] → a pixi `dev` feature in the default environment
    dev: Scope = Scope()
    envs: dict[str, Env] = {}  # [envs.<name>]    → pixi [feature]+[environments]
    env: dict[str, str] = {}  # env vars
    activation: Activation = Activation()  # [activation] scripts
    modules: Modules = Modules()  # [modules]  → HPC module stack for activate.sh
    tasks: dict[str, Task] = {}

    @model_validator(mode="after")
    def default_env_is_reserved(self) -> Self:
        """Reject `[envs.default]` because `default` is the implicit base environment."""
        if "default" in self.envs:
            raise ValueError("[envs.default] is reserved")
        return self

    @classmethod
    def load(cls, path: Path) -> Manifest:
        """Read and validate the manifest file into a typed manifest."""
        return cls.from_toml(path.read_text())

    @classmethod
    def from_toml(cls, text: str) -> Manifest:
        """Parse and validate a `chefe.toml` string."""
        return cls.model_validate(tomllib.loads(text))

    def declared(self, env: str, platform: str) -> dict[str, Declared]:
        """Every dep declared for ``env`` on ``platform``: name -> Declared(source, spec)."""
        scopes = self.active_scopes(env, platform)
        if env == "default":
            scopes.append(self.dev)
        return {
            name: Declared(source=source, spec=spec.version or "*")
            for scope in scopes
            for source, deps in scope.groups().items()
            for name, spec in deps.items()
        }

    def active_scopes(self, env: str, platform: str) -> list[Scope]:
        """Base, matching platform overlays, and the named env scope when active."""
        scopes: list[Scope] = [
            self,
            *(s for plat, s in self.on.items() if platform.startswith(plat)),
        ]
        if env != "default" and env in self.envs:
            scopes.append(self.envs[env])
        return scopes

    def toolchains_for(self, env: str, platform: str) -> dict[str, ToolchainSpec]:
        """Merged runtime-keyed toolchain specs for the active scopes."""
        scopes = self.active_scopes(env, platform)
        if env == "default":
            scopes.append(self.dev)
        merged: dict[str, ToolchainSpec] = {}
        for scope in scopes:
            for name, spec in scope.toolchains().items():
                merged[name] = merged[name].merge(spec) if name in merged else spec
        return merged

    def python(self) -> ToolchainSpec:
        """The root Python toolchain settings, if declared."""
        return self.toolchains().get("python", ToolchainSpec())
