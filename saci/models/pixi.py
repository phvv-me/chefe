"""The generated ``pixi.toml`` schema — a typed builder so the compile is typed on
both ends. Hyphenated pixi tables (``pypi-dependencies`` …) are aliases; serialise
with ``model_dump(by_alias=True, exclude_defaults=True)``.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from .base import FlexModel
from .manifest import Manifest, Spec, resolve


def pixi_task(spec: Any) -> Any:
    """Translate a mise-style task into pixi's (`run` -> `cmd`, `depends` -> `depends-on`)."""
    if isinstance(spec, str):
        return spec
    renamed = {"run": "cmd", "depends": "depends-on", "dir": "cwd"}
    return {renamed.get(key, key): value for key, value in spec.items()}


class PixiManifest(FlexModel):
    """What saci emits as ``.saci/pixi.toml``."""

    workspace: dict[str, Any]
    system_requirements: dict[str, str] = Field(default_factory=dict, alias="system-requirements")
    activation: dict[str, Any] = {}
    dependencies: dict[str, Spec] = {}
    pypi_dependencies: dict[str, Spec] = Field(default_factory=dict, alias="pypi-dependencies")
    pypi_options: dict[str, Any] = Field(default_factory=dict, alias="pypi-options")
    target: dict[str, Any] = {}
    feature: dict[str, Any] = {}
    environments: dict[str, Any] = {}
    tasks: dict[str, Any] = {}

    @classmethod
    def from_manifest(cls, m: Manifest) -> PixiManifest:
        """Build the pixi manifest from a validated saci :class:`Manifest`."""
        indexes = m.pypi.indexes
        activation = {k: v for k, v in m.env.items() if not k.startswith("_.")}
        return cls(
            workspace={
                "name": m.saci.name,
                "version": "0.1.0",
                "channels": m.saci.channels,
                "platforms": m.saci.platforms,
            },
            system_requirements=m.system,
            activation={"env": activation} if activation else {},
            dependencies=dict(m.deps),
            pypi_dependencies=resolve(m.pypi.deps, indexes),
            pypi_options=m.pypi.options(),
            target={plat: scope.tables(indexes) for plat, scope in m.on.items()},
            feature={name: env.feature(indexes) for name, env in m.envs.items()},
            environments={
                name: {"features": [name], **({"no-default-feature": True} if env.no_default else {})}
                for name, env in m.envs.items()
            },
            tasks={name: pixi_task(spec) for name, spec in m.tasks.items()},
        )
