from __future__ import annotations

import json
from pathlib import Path

from ..state import Installed
from .tool import Tool


class Npm(Tool):
    """The npm backend, scoped to a workspace's env dir, owning its `package.json`."""

    name = "npm"
    filename = "package.json"

    def __init__(self, out: Path) -> None:
        self.out = out
        self.manifest = out / self.filename

    def scope(self) -> tuple[str, ...]:
        return ("--prefix", str(self.out), "--no-audit", "--no-fund")

    def available(self) -> bool:
        return self.manifest.exists()

    def installed(self, env: str) -> dict[str, Installed]:
        manifests = (
            *self.out.glob("node_modules/*/package.json"),
            *self.out.glob("node_modules/@*/*/package.json"),
        )
        found = (json.loads(m.read_text()) for m in manifests)
        return {data["name"]: Installed(version=data["version"], kind="npm") for data in found}
