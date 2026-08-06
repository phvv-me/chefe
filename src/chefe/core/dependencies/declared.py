from ..base import Model


class Declared(Model):
    """A dependency as written in the manifest (keyed by name elsewhere).

    source: manifest group that declared it.
    spec: version constraint kept for display, since pixi owns the real resolution.
    """

    source: str
    spec: str
