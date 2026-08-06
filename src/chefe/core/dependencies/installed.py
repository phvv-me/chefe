from ..base import Model


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

    @property
    def source(self) -> str:
        """The manifest source this package's kind belongs to.

        pixi reports Python packages as `pypi` while the manifest declares them under
        `[python]`, and every other kind already carries the manifest's own name.
        """
        return "python" if self.kind == "pypi" else self.kind
