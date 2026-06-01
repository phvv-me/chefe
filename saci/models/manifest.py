"""The `saci.toml` input schema. pydantic validates *structure*; package *specs*
are pixi's job, validated at install.

A manifest is a base set of per-registry dep maps plus conditional overlays keyed
by platform or env — an overlay and an env share the same :class:`Scope` shape,
differing only by their condition. The transforms each part needs live on it as
methods, so the compile step is just ``PixiManifest.from_manifest(manifest)``.
"""

from __future__ import annotations

import platform
from typing import Any, TypeAlias

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version
from pydantic import Field

from .base import FlexModel

# A version spec is a bare string ("≥2.4") or an inline table carrying a source
# (version + index / url / git / path / channel / build / locked). TypeAlias keeps
# this 3.11-compatible (PEP 695 `type` would require 3.12+).
Spec: TypeAlias = str | dict[str, Any]


def resolve(deps: dict[str, Spec], indexes: dict[str, str]) -> dict[str, Spec]:
    """``deps`` with each named ``index`` swapped for its URL from ``[pypi.indexes]``."""
    return {
        package: {**spec, "index": indexes[spec["index"]]}
        if isinstance(spec, dict) and indexes.get(spec.get("index", ""))
        else spec
        for package, spec in deps.items()
    }


def current_platform() -> str:
    """This host's pixi platform, e.g. ``osx-arm64`` / ``linux-64`` / ``linux-aarch64``."""
    osname = {"Darwin": "osx", "Linux": "linux", "Windows": "win"}[platform.system()]
    arm = platform.machine() in ("arm64", "aarch64")
    arch = "aarch64" if arm and osname == "linux" else "arm64" if arm else "64"
    return f"{osname}-{arch}"


def satisfied(spec: str, version: str) -> bool:
    """Whether ``version`` meets ``spec`` (display-only; pixi is the real gate)."""
    if spec in ("*", ""):
        return True
    try:
        return Version(version) in SpecifierSet(spec)
    except (InvalidVersion, InvalidSpecifier):
        return True


class Registry(FlexModel):
    """A non-default registry's packages (pypi / cargo / npm / gem): one ``deps`` map."""

    deps: dict[str, Spec] = {}


class PyPI(Registry):
    """PyPI packages + named indexes; other keys (index-strategy, extra-index-urls)
    ride through as :class:`FlexModel` extras into pixi's ``[pypi-options]``."""

    indexes: dict[str, str] = {}

    def options(self) -> dict[str, Any]:
        """The extra (non-dep, non-index) settings → pixi ``[pypi-options]``."""
        return dict(self.model_extra or {})


class Scope(FlexModel):
    """A set of per-registry deps — shared by the base manifest, each platform overlay,
    and each environment. ``deps`` is conda (the default source)."""

    deps: dict[str, Spec] = {}
    pypi: PyPI = PyPI()
    cargo: Registry = Registry()
    npm: Registry = Registry()
    gem: Registry = Registry()

    def tables(self, indexes: dict[str, str]) -> dict[str, Any]:
        """This scope's conda + pypi deps as pixi tables."""
        out: dict[str, Any] = {}
        if self.deps:
            out["dependencies"] = dict(self.deps)
        if self.pypi.deps:
            out["pypi-dependencies"] = resolve(self.pypi.deps, indexes)
        return out


class Env(Scope):
    """A named environment (→ pixi feature + environment); may carry its own overlays."""

    on: dict[str, Scope] = {}
    no_default: bool = Field(default=False, alias="no-default")

    def feature(self, indexes: dict[str, str]) -> dict[str, Any]:
        """This env as a pixi feature: its registries + any nested platform overlays."""
        body = self.tables(indexes)
        for plat, scope in self.on.items():
            if scope.deps:
                body.setdefault("target", {})[plat] = {"dependencies": dict(scope.deps)}
        return body


class Header(FlexModel):
    """The ``[saci]`` table: identity + solve surface."""

    name: str
    platforms: list[str] = []
    channels: list[str] = ["conda-forge"]
    dotenv: bool = True


class Manifest(Scope):
    """The whole ``saci.toml``: a :class:`Scope` plus identity, conditions, env, tasks."""

    saci: Header
    system: dict[str, str] = {}                  # [system]  → pixi [system-requirements]
    on: dict[str, Scope] = {}                    # [on.<platform>]  → pixi [target.*]
    envs: dict[str, Env] = {}                    # [envs.<name>]    → pixi [feature]+[environments]
    env: dict[str, Any] = {}                     # env vars
    tasks: dict[str, Any] = {}

    def declared(self, env: str) -> dict[str, dict[str, str]]:
        """Every dep declared for ``env`` on this platform: name -> {spec, source}."""
        here = current_platform()
        out: dict[str, dict[str, str]] = {}

        def add(scope: Scope) -> None:
            for source, deps in (
                ("conda", scope.deps),
                ("pypi", scope.pypi.deps),
                ("cargo", scope.cargo.deps),
                ("npm", scope.npm.deps),
            ):
                for name, spec in deps.items():
                    version = spec.get("version", "*") if isinstance(spec, dict) else spec
                    out[name] = {"spec": version, "source": source}

        add(self)
        for key, scope in self.on.items():
            if here.startswith(key):
                add(scope)
        if env != "default" and (block := self.envs.get(env)):
            add(block)
        return out
