import json
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from functools import cached_property
from pathlib import Path

from plumbum import local
from plumbum.commands.base import BaseCommand
from plumbum.commands.processes import CommandNotFound

from ..state import Installed
from .tool import Tool

# chefe's engine. `pip install chefe` brings no binary, so chefe installs it on first use the
# way the old installer did, with the official script that drops `pixi` into `PIXI_HOME/bin`.
PIXI_INSTALLER = "curl -fsSL https://pixi.sh/install.sh | sh"


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

    def env_prefix(self, env: str) -> Path:
        """The provisioned pixi environment prefix for ``env``."""
        return self.manifest.parent / ".pixi" / "envs" / env

    @contextmanager
    def activated(self, env: str = "default") -> Iterator[None]:
        """Prepend the provisioned env's `bin/` to PATH for the duration of the block.

        `chefe install` puts a declared manager (pnpm/yarn/…) inside this env, not on the user's
        PATH, so a tool run straight afterward must see the env's `bin/` to be found at all. The
        env may not exist yet (a dry call before install), in which case PATH is left untouched.
        """
        binary = self.env_prefix(env) / "bin"
        path = local.env["PATH"]
        with local.env(PATH=f"{binary}{os.pathsep}{path}" if binary.is_dir() else path):
            yield

    def bootstrap(self) -> None:
        """Install pixi (chefe's engine) when it is missing, so `pip install chefe` is enough.

        Runs pixi's official installer, which places the binary in `PIXI_HOME/bin`; this is the
        one-time download the old `install.sh` did, now triggered lazily from chefe itself.
        """
        sys.stderr.write("chefe: installing pixi engine…\n")
        self.foreground(local["sh"]["-c", PIXI_INSTALLER])

    @cached_property
    def command(self) -> BaseCommand:
        """The pixi executable. Prefer it on PATH, fall back to `PIXI_HOME/bin` when a non-login
        remote shell has dropped it, and bootstrap the engine when it is absent everywhere."""
        try:
            return local["pixi"]
        except CommandNotFound:
            binary = self.home() / "bin" / "pixi"
            if not binary.exists():
                self.bootstrap()
            return local[str(binary)]

    def scope(self) -> tuple[str, ...]:
        return ("--manifest-path", str(self.manifest))

    def shell_hook(self, env: str = "default", shell: str = "bash") -> str:
        """The activation script for ``env``: the env vars, PATH, and `[activation] scripts`
        pixi sets when entering the env, emitted as a sourceable ``shell`` snippet.

        This is the exact activation `chefe run` performs, captured as text so a generated
        `activate.sh` can reproduce the whole pixi env without invoking pixi at job time.
        """
        return str(self.command["shell-hook", "-s", shell, "-e", env, *self.scope()]())

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
