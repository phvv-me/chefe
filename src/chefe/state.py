from .base import Model


class Installed(Model):
    """A package found provisioned in an environment (keyed by name elsewhere).

    pixi reports a null version for an editable or direct-path dependency (its source is a
    local checkout, not a registry pin), so ``version`` is optional and renders as ``(path)``.
    """

    version: str | None = None
    kind: str
    explicit: bool = True

    @property
    def shown_version(self) -> str:
        """The version to display: the pin, or ``(path)`` for an editable/path dep with none."""
        return self.version if self.version is not None else "(path)"


class Declared(Model):
    """A dependency as written in the manifest (keyed by name elsewhere)."""

    source: str
    spec: str  # version constraint, for display
