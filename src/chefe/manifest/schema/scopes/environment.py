from pydantic import Field

from ....core import Task, Toml
from .scope import Scope


class Env(Scope):
    """A named environment with dependencies, overlays, and tasks."""

    channels: list[str] = []
    on: dict[str, Scope] = {}
    tasks: dict[str, Task] = {}
    no_default: bool = Field(default=False, alias="no-default")
    platforms: list[str] = []
    system: dict[str, str] = {}

    def feature(self, indexes: dict[str, str]) -> dict[str, Toml]:
        """Compile this environment into Pixi feature tables."""
        body = self.tables(indexes)
        if self.channels:
            body["channels"] = self.channels
        if self.platforms:
            body["platforms"] = self.platforms
        target = {
            platform: tables
            for platform, scope in self.on.items()
            if (tables := scope.tables(indexes))
        }
        if target:
            body["target"] = target
        return body
