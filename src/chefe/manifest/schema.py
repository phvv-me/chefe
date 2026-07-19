import tomllib
from collections.abc import Mapping
from importlib.metadata import version
from pathlib import Path
from typing import Self

from pydantic import ConfigDict, Field, model_serializer, model_validator

from .. import NAME, PYPROJECT
from ..base import FlexModel, Model, Toml
from ..state import Declared
from ..utils import platform_scopes
from .pyproject import manifest_body

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


# Standalone package managers chefe provisions from `manager` alone: each one's conda-forge
# package name equals the manager name, so `[nodejs] manager = "pnpm"` (or yarn/bun, or
# `[python] manager = "uv"`) needs no redundant entry in `[deps]`. npm/pip/cargo ship with
# their runtime, and a compiler or other `manager` executable is provisioned via its own
# runtime package, so neither is listed here.
PROVISIONABLE_MANAGERS = frozenset({"pnpm", "yarn", "bun", "uv"})


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

    def manager_package(self) -> str | None:
        """The conda package to provision for a standalone manager, or None.

        Lets `[nodejs] manager = "pnpm"` (or yarn/bun, or `[python] manager = "uv"`) provision
        the manager itself, so it need not be repeated in `[deps]`.
        """
        return self.manager if self.manager in PROVISIONABLE_MANAGERS else None

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

    def toolchains(self) -> dict[str, ToolchainSpec]:
        """Runtime-keyed toolchain tables carried by this scope.

        Declaration of the runtime itself is enforced once, at the manifest level, against
        the union of this scope's and the root `[deps]`, so an overlay like
        `[on.linux.python.deps]` needs no redundant local `python = "*"`.
        """
        extras = self.model_extra or {}
        return {
            name: ToolchainSpec.model_validate(spec)
            for name, spec in extras.items()
            if isinstance(spec, Mapping)
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
        out: dict[str, Toml] = {}
        dependencies: dict[str, Toml] = {name: spec.to_toml() for name, spec in self.deps.items()}
        # Provision a non-bundled toolchain manager (pnpm/yarn/bun/uv) unless already pinned.
        for toolchain in self.toolchains().values():
            if (pkg := toolchain.manager_package()) and pkg not in dependencies:
                dependencies[pkg] = "*"
        if dependencies:
            out["dependencies"] = dependencies
        if (python := self.toolchains().get("python")) and python.all_deps():
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
    system: dict[str, str] = {}  # per-env virtual-package floor

    def feature(self, indexes: dict[str, str]) -> dict[str, Toml]:
        """This env as a Pixi feature with registries, platform limits, and overlays."""
        body: dict[str, Toml] = {}
        body.update(self.tables(indexes))
        if self.platforms:
            body["platforms"] = self.platforms
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

    Each pair renders to one ``module load name/version`` spec, in declared order. For example
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
    system: dict[str, str] = {}  # [system] → virtual packages on compiled platforms
    on: dict[str, Scope] = {}  # [on.<platform>]  → pixi [target.*]
    # [dev.*] → a pixi `dev` feature in the default environment
    dev: Scope = Scope()
    envs: dict[str, Env] = {}  # [envs.<name>]    → pixi [feature]+[environments]
    env: dict[str, str] = {}  # env vars
    activation: Activation = Activation()  # [activation] scripts
    modules: Modules = Modules()  # [modules]  → HPC module stack for activate.sh
    tasks: dict[str, Task] = {}

    @model_validator(mode="after")
    def reserved_env_names(self) -> Self:
        """Reject `[envs.default]` and `[envs.dev]`: the base manifest is the default
        environment and `[dev]` already compiles to the `dev` feature."""
        if reserved := {"default", "dev"} & set(self.envs):
            names = ", ".join(f"[envs.{name}]" for name in sorted(reserved))
            raise ValueError(
                f"{names} is reserved. The base manifest is the default environment and "
                "[dev] is the dev feature, so use another env name."
            )
        return self

    @model_validator(mode="after")
    def toolchain_tables_must_be_declared(self) -> Self:
        """Reject a runtime-keyed table whose runtime is in neither its scope's nor root `[deps]`.

        The usual cause is a table from a newer chefe than the one installed, so the message leads
        with the upgrade path (naming the running version) before the declare-or-remove fix.
        """
        root = frozenset(self.deps)
        scopes: list[tuple[str, Scope, frozenset[str]]] = [("", self, root)]
        scopes.append(("dev.", self.dev, root))
        scopes += [(f"on.{plat}.", scope, root) for plat, scope in self.on.items()]
        for name, env in self.envs.items():
            local = root | frozenset(env.deps)
            scopes.append((f"envs.{name}.", env, local))
            scopes += [(f"envs.{name}.on.{plat}.", scope, local) for plat, scope in env.on.items()]
        missing = sorted(
            f"[{at}{table}]"
            for at, scope, allowed in scopes
            for table, spec in (scope.model_extra or {}).items()
            if isinstance(spec, Mapping) and table not in allowed | frozenset(scope.deps)
        )
        if missing:
            raise ValueError(
                f"{', '.join(missing)} has no matching package in [deps]. This is often a table "
                f"from a newer {NAME} than the {version(NAME)} you have, so try "
                f"`pip install -U {NAME}`, otherwise add it to [deps] or remove it."
            )
        return self

    @classmethod
    def load(cls, path: Path) -> Manifest:
        """Read and validate a `chefe.toml`, or a `pyproject.toml` carrying `[tool.chefe]`."""
        text = path.read_text()
        return cls.from_pyproject(text) if path.name == PYPROJECT else cls.from_toml(text)

    @classmethod
    def from_toml(cls, text: str) -> Manifest:
        """Parse and validate a `chefe.toml` string."""
        return cls.model_validate(tomllib.loads(text))

    @classmethod
    def from_pyproject(cls, text: str) -> Manifest:
        """Parse a `pyproject.toml` string, reading `[tool.chefe]` and inheriting `[project]`."""
        return cls.model_validate(manifest_body(text))

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
        """The scopes contributing deps for ``env`` on ``platform``.

        A `no-default` env stands alone (pixi excludes the base feature there), and a named
        env brings its own platform overlays. Platform matching covers families, so
        `[on.linux]` and `[on.unix]` are active on `linux-64`.
        """
        selectors = platform_scopes(platform)
        named = self.envs.get(env) if env != "default" else None
        scopes: list[Scope] = []
        if named is None or not named.no_default:
            scopes += [self, *(s for plat, s in self.on.items() if plat in selectors)]
        if named is not None:
            scopes += [named, *(s for plat, s in named.on.items() if plat in selectors)]
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
