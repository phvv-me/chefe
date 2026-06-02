from __future__ import annotations

from .base import Model


class Installed(Model):
    """A package found provisioned in an environment (keyed by name elsewhere)."""

    version: str
    kind: str  # conda | pypi | npm | cargo
    explicit: bool = True


class Declared(Model):
    """A dependency as written in the manifest (keyed by name elsewhere)."""

    source: str  # conda | pypi | cargo | npm | gem
    spec: str  # version constraint, for display
