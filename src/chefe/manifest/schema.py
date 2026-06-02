from __future__ import annotations

import tomllib
from enum import StrEnum
from pathlib import Path

from pydantic import ConfigDict, Field, model_serializer, model_validator

from ..base import FlexModel, Model, Toml
from ..state import Declared

# A pixi/mise task: a bare command string, or a table (run/cmd, depends, cwd, ...).
Task = str | dict[str, Toml]


class Spec(FlexModel):
    """A dependency spec: a bare version string, or an inline table carrying a source.

    `version` and `index` are the keys we read (index resolves against `[pypi.indexes]`); any
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
        """This spec with a named `index` swapped for its URL from `[pypi.indexes]`."""
        if self.index in indexes:
            return self.model_copy(update={"index": indexes[self.index]})
        return self


class Registry(Model):
    """A non-default registry's packages (pypi / cargo / npm / gem): one ``deps`` map."""

    deps: dict[str, Spec] = {}


class PyPI(Registry):
    """PyPI packages + named indexes; other keys (index-strategy, extra-index-urls)
    ride through as extras into pixi's ``[pypi-options]``."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    indexes: dict[str, str] = {}

    def options(self) -> dict[str, Toml]:
        """The extra (non-dep, non-index) settings → pixi ``[pypi-options]``."""
        return {key: value for key, value in (self.model_extra or {}).items()}


class Runtime(StrEnum):
    """The conda-forge language runtime each non-conda ecosystem needs to install and run.

    The member name is the ecosystem, its value the package we ensure in `[deps]` so a
    `[pypi.deps]` without an explicit `python` still works, the same for node/rust/ruby.
    """

    pypi = "python"
    npm = "nodejs"
    cargo = "rust"
    gem = "ruby"


class Scope(Model):
    """A set of per-registry deps, shared by the base manifest, each platform overlay,
    and each environment. `deps` is conda, the default source."""

    deps: dict[str, Spec] = {}
    pypi: PyPI = PyPI()
    cargo: Registry = Registry()
    npm: Registry = Registry()
    gem: Registry = Registry()

    def registries(self) -> dict[str, Registry]:
        """The non-conda registries by source name, discovered from the model's own fields."""
        return {name: value for name, value in self if isinstance(value, Registry)}

    def groups(self) -> dict[str, dict[str, Spec]]:
        """Every dep group by source name: conda plus each ecosystem registry."""
        return {"conda": self.deps, **{name: reg.deps for name, reg in self.registries().items()}}

    def tables(self, indexes: dict[str, str]) -> dict[str, Toml]:
        """This scope as pixi tables: conda `deps` (runtimes ensured) plus pypi.

        Each spec renders to its TOML form (a version string or an inline table), so the
        result is a plain nested `Toml` that pixi validates back into `Spec` on its own fields.
        """
        deps = dict(self.deps)
        for name, registry in self.registries().items():
            if registry.deps:
                deps.setdefault(Runtime[name].value, Spec(version="*"))
        out: dict[str, Toml] = {}
        if deps:
            out["dependencies"] = {name: spec.to_toml() for name, spec in deps.items()}
        if self.pypi.deps:
            out["pypi-dependencies"] = {
                name: spec.with_index(indexes).to_toml() for name, spec in self.pypi.deps.items()
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


class Manifest(Scope):
    """The whole manifest: a :class:`Scope` plus identity, conditions, env, tasks."""

    workspace: Header
    system: dict[str, str] = {}  # [system]  → pixi [system-requirements]
    on: dict[str, Scope] = {}  # [on.<platform>]  → pixi [target.*]
    envs: dict[str, Env] = {}  # [envs.<name>]    → pixi [feature]+[environments]
    env: dict[str, str] = {}  # env vars
    activation: Activation = Activation()  # [activation] scripts
    tasks: dict[str, Task] = {}

    @classmethod
    def load(cls, path: Path) -> Manifest:
        """Read and validate the manifest file into a typed manifest."""
        return cls.model_validate(tomllib.loads(path.read_text()))

    def declared(self, env: str, platform: str) -> dict[str, Declared]:
        """Every dep declared for ``env`` on ``platform``: name -> Declared(source, spec)."""
        scopes: list[Scope] = [
            self,
            *(s for plat, s in self.on.items() if platform.startswith(plat)),
        ]
        if env != "default" and env in self.envs:
            scopes.append(self.envs[env])
        return {
            name: Declared(source=source, spec=spec.version or "*")
            for scope in scopes
            for source, deps in scope.groups().items()
            for name, spec in deps.items()
        }
