from typing import Annotated

from cyclopts import Parameter
from plumbum import local
from plumbum.commands.processes import CommandNotFound

from ...backends import Pixi
from ...core import ChefeError
from ..layout import Workspace
from ..runtime import Runtime


class ExecutionCommands:
    """`chefe run|x|shell`: everything that hands control to a program in or beside the env."""

    def __init__(self, workspace: Workspace, runtime: Runtime, pixi: Pixi) -> None:
        self.workspace = workspace
        self.runtime = runtime
        self.pixi = pixi

    def env_from(self, argv: tuple[str, ...]) -> tuple[str, tuple[str, ...]]:
        """Split a leading `--env/-e <name>` off the command line, returning `(env, rest)`.

        `rest` is the command to run with the env flag removed and must be non-empty (its
        first token is the task or executable). A missing command, an `--env` without a
        following name, or one not naming a declared `[envs.*]` is a `ChefeError` so the
        mistake fails fast rather than reaching pixi as a confusing bare error.
        """
        if argv and argv[0] in ("--env", "-e"):
            if len(argv) < 3:
                raise ChefeError("`--env` needs an environment name and a command to run.")
            env, rest = argv[1], argv[2:]
        else:
            env, rest = "default", argv
        if not rest:
            raise ChefeError("`chefe run` needs a task or executable to run.")
        declared = self.workspace.load().envs
        if env != "default" and env not in declared:
            names = ", ".join(sorted(declared)) or "(none)"
            raise ChefeError(
                f"No environment `{env}` is declared. Add an `[envs.{env}]` table or use one of: "
                f"{names}."
            )
        return env, rest

    def require_runnable(self, head: str, *, env: str) -> None:
        """Fail with guidance when ``head`` is neither a declared task nor an executable on PATH.

        Must be called from inside the activated env, since that is what puts the installed
        executables where the lookup can see them.
        """
        manifest = self.workspace.load()
        tasks = manifest.tasks if env == "default" else manifest.envs[env].tasks
        table = "[tasks]" if env == "default" else f"[envs.{env}.tasks]"
        if head in tasks:
            return
        try:
            local[head]
        except CommandNotFound as error:
            raise ChefeError(
                f"No task or executable named `{head}` was found in the `{env}` environment. "
                f"Run `chefe install`, check `chefe tree`, or add it to {table}."
            ) from error

    def run(self, *argv: Annotated[str, Parameter(allow_leading_hyphen=True)]) -> None:
        """Run a task or installed executable inside the env, exiting with its code.

        Declared `[tasks]` come first; any other name falls through to an executable on the
        activated PATH. Both go through `pixi run` so the manifest's `[activation]` scripts
        and env vars always apply. A name that is neither fails with guidance up front,
        instead of pixi's bare command-not-found.

        A leading `--resolve` permits Pixi to update an existing lock on this machine. A leading
        `--env <name>` (or `-e <name>`) then selects a non-default `[envs.*]` environment, e.g.
        `chefe run --resolve --env serving python ...`. The whole command line is taken as one
        leading-hyphen var-positional so chefe's flags and target flags arrive verbatim. Help
        flags ride along too. `chefe run atpx --help` prints atpx's help, and this page appears
        only when no task name precedes the flag, as in `chefe run --help`.
        """
        resolve = argv[:1] == ("--resolve",)
        env, rest = self.env_from(argv[1:] if resolve else argv)
        with self.runtime.activated(env):
            self.require_runnable(rest[0], env=env)
            code = self.pixi.launch("run", *rest, env=env, resolve=resolve)
        if code:
            raise SystemExit(code)

    def shell(self, env: str = "default", *, resolve: bool = False) -> None:
        """Open an activated shell in ``env``, exiting with the shell's own status."""
        with self.runtime.activated(env):
            code = self.pixi.enter(env, resolve=resolve)
        if code:
            raise SystemExit(code)

    def x(
        self,
        *args: Annotated[str, Parameter(allow_leading_hyphen=True)],
        with_: tuple[str, ...] = (),
    ) -> None:
        """Run a command in a throwaway env, like uvx or pipx run; no manifest needed.

        args: the command and its arguments, e.g. `chefe x ruff check .`.
        with_: extra packages to make available, e.g. `--with build`.
        """
        if code := self.pixi.exec(with_, args):
            raise SystemExit(code)
