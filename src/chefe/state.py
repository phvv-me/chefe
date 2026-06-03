from .base import Model


class Installed(Model):
    """A package found provisioned in an environment (keyed by name elsewhere)."""

    version: str
    kind: str
    explicit: bool = True


class Declared(Model):
    """A dependency as written in the manifest (keyed by name elsewhere)."""

    source: str
    spec: str  # version constraint, for display
