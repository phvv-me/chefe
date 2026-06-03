import tomllib
from pathlib import Path

from ..state import Installed
from .pixi import Pixi
from .tool import Tool


class Cargo(Tool):
    """The cargo backend: crates install into the pixi env prefix, so they share its PATH.

    cargo lives inside the pixi env, so every command runs through `pixi run cargo`.
    """

    def __init__(self, out: Path, pixi: Pixi) -> None:
        self.out = out
        self.pixi = pixi

    def __call__(self, verb: str, *args: str, **flags: bool | str | None) -> bool:
        return self.pixi("run", "cargo", verb, *args, **flags)

    def root(self, env: str) -> Path:
        """The pixi env prefix; crates install here so they share the env's activated PATH."""
        return self.pixi.env_prefix(env)

    def installed(self, env: str) -> dict[str, Installed]:
        crates = self.root(env) / ".crates.toml"
        try:
            entries = tomllib.loads(crates.read_text()).get("v1", {})
        except FileNotFoundError:
            return {}
        return {
            parts[0]: Installed(version=parts[1], kind="cargo")
            for key in entries
            if (parts := key.split())
        }

    def sync(self, env: str, declared: dict[str, str]) -> None:
        """Make ``env``'s crates match ``declared`` exactly: install missing, uninstall removed."""
        at = str(self.root(env))
        have = self.installed(env)
        for name in have.keys() - declared.keys():
            self("uninstall", "--root", at, name)
        for name, spec in declared.items():
            if name not in have:
                version = () if spec in ("*", "") else ("--version", spec)
                self("install", "--root", at, *version, name)
