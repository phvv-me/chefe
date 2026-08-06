import json
from pathlib import Path

from plumbum import local

from ...core import ChefeError
from ..base.process import Process
from .engine import PixiEngine


class PixiGlobal:
    """The `pixi global ...` surface: envs shared across every workspace on this machine.

    Conda specs go through pixi itself, while pip, npm, and cargo run from inside the global
    env's own prefix, which is why each of those takes the prefix rather than the env name.
    None of this refines how a pixi command is built or run, so the engine is held rather than
    inherited and only its executable, flags, and home are used.
    """

    def __init__(self) -> None:
        self.engine = PixiEngine()

    def add(self, name: str, specs: tuple[str, ...]) -> None:
        """Add conda specs to global env ``name``, creating the env first if it is missing.

        `pixi global add` requires an existing `--environment`, while `pixi global install`
        creates one on demand and is additive for an existing env, so the latter verb covers
        both the create and the add and chefe picks it whenever the env is not there yet.
        """
        verb = "add" if self.exists(name) else "install"
        argv = ("global", verb, *self.engine.flags(environment=name), *specs)
        if not Process.foreground(self.engine.command[argv]):
            raise ChefeError("`pixi global add` failed (see its output above)")

    def cargo(self, prefix: Path, specs: list[str]) -> None:
        """Install cargo ``specs`` into the global env's prefix with its own cargo."""
        cargo = local[str(prefix / "bin" / "cargo")]
        if not Process.foreground(cargo["install", "--root", str(prefix), *specs]):
            raise ChefeError("global cargo install failed (see its output above)")

    def exists(self, name: str) -> bool:
        """Whether a global env named ``name`` already exists (per `pixi global list`)."""
        command = self.engine.command["global", "list", "--json"]
        envs = json.loads(Process.output(command, "pixi global list"))
        return any(env["name"] == name for env in envs)

    def install(self, name: str, specs: list[str]) -> None:
        """Install conda ``specs`` into a shared global pixi env named ``name``."""
        argv = ("global", "install", *self.engine.flags(environment=name), *specs)
        if not Process.foreground(self.engine.command[argv]):
            raise ChefeError("`pixi global install` failed (see its output above)")

    def npm(self, prefix: Path, specs: list[str]) -> None:
        """Globally install npm ``specs`` with the global env's npm."""
        if not Process.foreground(local[str(prefix / "bin" / "npm")]["install", "-g", *specs]):
            raise ChefeError("global npm install failed (see its output above)")

    def pip(self, prefix: Path, specs: list[str]) -> None:
        """Install pypi ``specs`` into the global env's Python with its own pip."""
        python = local[str(prefix / "bin" / "python")]
        if not Process.foreground(python["-m", "pip", "install", *specs]):
            raise ChefeError("global pip install failed (see its output above)")

    def prefix(self, name: str) -> Path:
        """The prefix of global env ``name``; its `bin/` holds python/npm/cargo."""
        return self.engine.home() / "envs" / name

    def remove(self, name: str, packages: tuple[str, ...]) -> None:
        """Remove conda packages from a shared global pixi env named ``name``."""
        argv = ("global", "remove", *self.engine.flags(environment=name), *packages)
        if not Process.foreground(self.engine.command[argv]):
            raise ChefeError("`pixi global remove` failed (see its output above)")

    def show(
        self, name: str = "", *, regex: str = "", json: bool = False, sort_by: str = ""
    ) -> None:
        """List all global envs, or packages inside one shared global pixi env."""
        argv = (
            "global",
            "list",
            *self.engine.flags(environment=name, json=json, sort_by=sort_by),
            *([regex] if regex else []),
        )
        if not Process.foreground(self.engine.command[argv]):
            raise ChefeError("`pixi global list` failed (see its output above)")
