import json
import os
import tomllib
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from functools import cached_property
from pathlib import Path

from plumbum import local
from plumbum.commands.base import BaseCommand

from ...core import ChefeError, Installed
from ..base.process import Process
from ..base.result import CommandResult
from ..base.tool import Tool
from .engine import PixiEngine


class Pixi(Tool):
    """The one seam to the pixi binary, pinned to the `pixi.toml` it owns in a workspace env dir.

    Every command that provisions, queries, or enters an environment goes through this class on
    purpose, so the lock rules, the drift diagnosis, and the manifest path a subprocess is pinned
    to are stated once. That is why so much of chefe depends on it and why it depends on so
    little: the argv building comes from :class:`Tool`, running a child belongs to
    :class:`Process`, and what comes back is a :class:`CommandResult` or an :class:`Installed`.

    Finding the executable (and installing it the first time) is a different job from owning a
    workspace manifest, so :class:`PixiEngine` is held rather than inherited, exactly as
    :class:`PixiGlobal` holds it, and only its resolved command and manifest-free `exec` are used.
    """

    name = "pixi"
    filename = "pixi.toml"

    def __init__(self, out: Path) -> None:
        self.engine = PixiEngine()
        self.manifest = out / self.filename

    @cached_property
    def command(self) -> BaseCommand:
        """The pixi executable, resolved (and bootstrapped when absent) by the engine."""
        return self.engine.command

    @property
    def lock(self) -> Path:
        """The lock file paired with chefe's compiled Pixi manifest."""
        return self.manifest.with_suffix(".lock")

    @contextmanager
    def activated(self, env: str = "default") -> Generator[None]:
        """Prepend the provisioned env's `bin/` to PATH for the duration of the block.

        `chefe install` puts a declared manager (pnpm/yarn/…) inside this env, not on the user's
        PATH, so a tool run straight afterward must see the env's `bin/` to be found at all. The
        env may not exist yet (a dry call before install), in which case PATH is left untouched.
        """
        binary = self.env_prefix(env) / "bin"
        path = local.env["PATH"]
        with local.env(PATH=f"{binary}{os.pathsep}{path}" if binary.is_dir() else path):
            yield

    def enter(self, env: str, *, resolve: bool = False) -> int:
        """Hand the terminal to an interactive shell inside ``env``, returning its exit code.

        A subshell owns the terminal, so it cannot go through :meth:`launch`, whose retained
        output seam would leave the user typing into a screen nothing redraws. Provisioning
        happens first through the ordinary locked install, which is where drift is diagnosed
        and reported, and only then does the shell take over the tty.
        """
        self.install(env, resolve=resolve)
        return Process.handover(self.command[("shell", *self.scope(), "-e", env)])

    def env_prefix(self, env: str) -> Path:
        """The provisioned pixi environment prefix for ``env``."""
        return self.manifest.parent / ".pixi" / "envs" / env

    def environment_result(self, verb: str, *args: str, resolve: bool = False) -> CommandResult:
        """Run an environment verb and retain its streamed native output."""
        if not resolve and not self.lock.exists():
            raise ChefeError(
                "pixi.lock is missing. Run `chefe install --resolve` on a solve-capable "
                "machine to create and verify the generated manifest/lock pair."
            )
        return self.within_cwd(
            Process.stream,
            verb,
            *args,
            locked=not resolve and not self._has_editable_paths(),
            frozen=not resolve and self._has_editable_paths(),
        )

    def _has_editable_paths(self) -> bool:
        """Whether the generated manifest carries a mutable editable Python source."""
        try:
            manifest = tomllib.loads(self.manifest.read_text())
        except FileNotFoundError:
            return False

        pending = [manifest]
        while pending:
            value = pending.pop()
            if isinstance(value, dict):
                if isinstance(value.get("path"), str) and value.get("editable") is True:
                    return True
                pending.extend(value.values())
            elif isinstance(value, list):
                pending.extend(value)
        return False

    def exec(self, specs: Sequence[str], args: tuple[str, ...]) -> int:
        """Run ``args`` in a throwaway env, returning its exit code.

        The env is resolved from the command line rather than from this workspace's manifest,
        so the engine answers it directly and nothing here is pinned.
        """
        return self.engine.exec(specs, args)

    def install(self, env: str, *, resolve: bool = False) -> None:
        """Install ``env`` locked by default and verify every explicitly resolved lock."""
        locked = not resolve
        result = self.environment_result("install", "-e", env, resolve=resolve)
        self._raise_on_lock_drift(result, locked=locked)
        if result.returncode:
            raise ChefeError("`pixi install` failed (see its output above)")
        if resolve:
            self.install(env)

    def installed(self, env: str) -> dict[str, Installed]:
        command = self.command["list", *self.scope(), "-e", env, "--json"]
        records = json.loads(Process.output(command, "pixi list"))
        return {
            rec["name"]: Installed(
                version=rec.get("version"), kind=rec["kind"], explicit=rec["is_explicit"]
            )
            for rec in records
        }

    def launch(self, verb: str, *args: str, env: str, resolve: bool = False) -> int:
        """Launch a task locked by default, diagnosing drift before task startup."""
        locked = not resolve
        result = self.environment_result(verb, "-e", env, *args, resolve=resolve)
        self._raise_on_lock_drift(result, locked=locked)
        return result.returncode

    def scope(self) -> tuple[str, ...]:
        return ("--manifest-path", str(self.manifest))

    def shell_hook(self, env: str = "default", *, shell: str = "bash") -> str:
        """The activation script for ``env`` as a sourceable ``shell`` snippet.

        It carries the env vars, PATH, and `[activation] scripts` pixi sets when entering the
        env.

        This is the exact activation `chefe run` performs, captured as text so a generated
        `activate.sh` can reproduce the whole pixi env without invoking pixi at job time.
        """
        command = self.command["shell-hook", "-s", shell, "-e", env, *self.scope()]
        return Process.output(command, "pixi shell-hook")

    @staticmethod
    def _raise_on_lock_drift(result: CommandResult, *, locked: bool) -> None:
        """Turn Pixi's pre-task lock rejection into chefe's actionable recovery message."""
        failure = f"{result.stdout}\n{result.stderr}".lower().replace("-", " ")
        task_started = "pixi task (" in failure
        if (
            result.returncode
            and locked
            and not task_started
            and "lock file" in failure
            and "not up to date" in failure
        ):
            raise ChefeError(
                "chefe.toml drifted from pixi.lock. Run `chefe install --resolve` on a "
                "solve-capable machine and reship `.chefe/pixi.toml` with "
                "`.chefe/pixi.lock`, or pass `--resolve` to solve here."
            )
