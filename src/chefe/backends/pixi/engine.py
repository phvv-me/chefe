import os
import sys
from collections.abc import Sequence
from functools import cached_property
from pathlib import Path

from plumbum import local
from plumbum.commands.base import BaseCommand
from plumbum.commands.processes import CommandNotFound

from ...core import ChefeError
from ..base.process import Process
from ..base.tool import Tool

# chefe's engine. `pip install chefe` brings no binary, so chefe installs it on first use the
# way the old installer did, with the official script that drops `pixi` into `PIXI_HOME/bin`.
_PIXI_INSTALLER = "curl -fsSL https://pixi.sh/install.sh | sh"


class PixiEngine(Tool):
    """Where the pixi binary is, and what it can do without a workspace to point at.

    Both the workspace-scoped backend and the global one need the same executable, so finding
    it (and installing it the first time) lives here alone. `exec` belongs here too, since a
    throwaway env is resolved from the command line rather than from any manifest.
    """

    name = "pixi"

    @cached_property
    def command(self) -> BaseCommand:
        """The pixi executable.

        Prefer it on PATH, fall back to `PIXI_HOME/bin` when a non-login remote shell has
        dropped it, and bootstrap the engine when it is absent everywhere.
        """
        try:
            return local["pixi"]
        except CommandNotFound:
            return local[str(self.installed_binary())]

    @staticmethod
    def home() -> Path:
        """pixi's home, where its `bin/` and global `envs/` live."""
        return Path(os.environ.get("PIXI_HOME") or Path.home() / ".pixi")

    def bootstrap(self) -> None:
        """Install pixi (chefe's engine) when it is missing, so `pip install chefe` is enough.

        Runs pixi's official installer, which places the binary in `PIXI_HOME/bin`; this is the
        one-time download the old `install.sh` did, now triggered lazily from chefe itself.
        """
        sys.stderr.write("chefe: installing pixi engine…\n")
        if not Process.foreground(local["sh"]["-c", _PIXI_INSTALLER]):
            raise ChefeError("the pixi installer failed; install it manually from https://pixi.sh")

    def exec(self, specs: Sequence[str], args: tuple[str, ...]) -> int:
        """Run ``args`` in a throwaway env (like uvx), returning the command's exit code.

        Extra ``specs`` ride along as `--spec`. The code is preserved rather than collapsed
        to a bool so `chefe x` exits with whatever the wrapped command exited.
        """
        spec_flags = [flag for spec in specs for flag in ("--spec", spec)]
        return Process.passthrough(self.command["exec", *spec_flags, *args])

    def installed_binary(self) -> Path:
        """Return the fallback Pixi binary after bootstrapping it when absent."""
        binary = self.home() / "bin" / "pixi"
        if not binary.exists():
            self.bootstrap()
        return binary
