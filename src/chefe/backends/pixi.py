from __future__ import annotations

import json
from pathlib import Path

from ..state import Installed
from .tool import Tool


class Pixi(Tool):
    """The pixi backend, pinned to the `pixi.toml` it owns inside a workspace's env dir."""

    name = "pixi"
    filename = "pixi.toml"

    def __init__(self, out: Path) -> None:
        self.manifest = out / self.filename

    def scope(self) -> tuple[str, ...]:
        return ("--manifest-path", str(self.manifest))

    def installed(self, env: str) -> dict[str, Installed]:
        records = json.loads(self.command["list", *self.scope(), "-e", env, "--json"]())
        return {
            rec["name"]: Installed(
                version=rec["version"], kind=rec["kind"], explicit=rec["is_explicit"]
            )
            for rec in records
        }

    def global_install(self, name: str, specs: list[str]) -> bool:
        """Install conda ``specs`` into a shared global pixi env named ``name``."""
        argv = ("global", "install", *self.flags(environment=name), *specs)
        return self.foreground(self.command[argv])
