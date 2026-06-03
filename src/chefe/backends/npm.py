import json
from pathlib import Path

from ..state import Installed
from .tool import Tool


class Node(Tool):
    """The JS backend: it runs whichever package manager a project names, in the env dir.

    npm, pnpm, yarn, and any future compatible tool all read the same `package.json` and write the
    same `node_modules`, so the only thing chefe needs is the binary to call. Each installs into
    its working directory by default, so running in `out` targets the env without a per-tool
    directory flag and a new manager needs no code here, only its name in `[nodejs] manager`.
    """

    filename = "package.json"

    def __init__(self, out: Path, manager: str = "npm") -> None:
        self.out = out
        self.name = manager
        self.manifest = out / self.filename

    def available(self) -> bool:
        return self.manifest.exists()

    def cwd(self) -> Path:
        return self.out

    def binary_dir(self) -> Path:
        """Directory where installed npm package executables are linked."""
        return self.out / "node_modules" / ".bin"

    def installed(self, env: str) -> dict[str, Installed]:
        manifests = (
            *self.out.glob("node_modules/*/package.json"),
            *self.out.glob("node_modules/@*/*/package.json"),
        )
        found = (json.loads(m.read_text()) for m in manifests)
        return {data["name"]: Installed(version=data["version"], kind="npm") for data in found}
