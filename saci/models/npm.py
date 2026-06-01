"""The generated ``package.json`` schema (from ``[npm.deps]``)."""

from __future__ import annotations

from .base import FlexModel
from .manifest import Manifest


class PackageJson(FlexModel):
    """What saci emits as ``.saci/package.json``."""

    name: str
    private: bool = True
    dependencies: dict[str, str] = {}

    @classmethod
    def from_manifest(cls, m: Manifest) -> PackageJson | None:
        """Build package.json from ``[npm.deps]``, or None if there are none."""
        if not m.npm.deps:
            return None
        return cls(
            name=f"{m.saci.name}-npm",
            dependencies={
                package: spec if isinstance(spec, str) else spec.get("version", "*")
                for package, spec in m.npm.deps.items()
            },
        )
