import json
import os
from functools import cached_property
from pathlib import Path

from plumbum import local
from plumbum.commands.base import BaseCommand
from plumbum.commands.processes import CommandNotFound

from ..state import Installed
from .tool import Tool


class Pixi(Tool):
    """The pixi backend, pinned to the `pixi.toml` it owns inside a workspace's env dir."""

    name = "pixi"
    filename = "pixi.toml"

    def __init__(self, out: Path) -> None:
        self.manifest = out / self.filename

    @staticmethod
    def home() -> Path:
        """pixi's home, where its `bin/` and global `envs/` live."""
        return Path(os.environ.get("PIXI_HOME") or Path.home() / ".pixi")

    @cached_property
    def command(self) -> BaseCommand:
        """The pixi executable; fall back to pixi's default dir when a non-login
        remote shell has dropped `~/.pixi/bin` from PATH."""
        try:
            return local["pixi"]
        except CommandNotFound:
            return local[str(self.home() / "bin" / "pixi")]

    def scope(self) -> tuple[str, ...]:
        return ("--manifest-path", str(self.manifest))

    def global_prefix(self, name: str) -> Path:
        """The prefix of global env ``name``; its `bin/` holds python/npm/cargo."""
        return self.home() / "envs" / name

    def global_pip(self, prefix: Path, specs: list[str]) -> bool:
        """Install pypi ``specs`` into the global env's Python with its own pip."""
        return self.foreground(
            local[str(prefix / "bin" / "python")]["-m", "pip", "install", *specs]
        )

    def global_npm(self, prefix: Path, specs: list[str]) -> bool:
        """Globally install npm ``specs`` with the global env's npm."""
        return self.foreground(local[str(prefix / "bin" / "npm")]["install", "-g", *specs])

    def global_cargo(self, prefix: Path, specs: list[str]) -> bool:
        """Install cargo ``specs`` into the global env's prefix with its own cargo."""
        cargo = local[str(prefix / "bin" / "cargo")]
        return self.foreground(cargo["install", "--root", str(prefix), *specs])

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

    def exec(self, specs: tuple[str, ...], args: tuple[str, ...]) -> bool:
        """Run ``args`` in a throwaway env (like uvx), pulling extra ``specs`` as `--spec`."""
        spec_flags = tuple(flag for spec in specs for flag in ("--spec", spec))
        return self.foreground(self.command["exec", *spec_flags, *args])
