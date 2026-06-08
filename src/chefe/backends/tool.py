from collections.abc import Callable
from functools import cached_property
from pathlib import Path
from typing import TypeVar

from plumbum import FG, TF, local
from plumbum.commands.base import BaseCommand
from plumbum.commands.processes import ProcessExecutionError

from ..state import Installed

T = TypeVar("T")


class Tool:
    """A package-manager backend: call it to run a foreground command, query what's installed.

    Subclasses set ``name`` and override ``scope`` (args that pin the command to the workspace)
    and ``available`` (a guard). ``installed`` is theirs to implement per ecosystem.

    plumbum is untyped, so this class is the single seam that touches it: every foreground run
    funnels through ``foreground`` (which hands back a real `bool`), keeping the rest of the
    codebase free of the `Any` that plumbum's `& TF(FG=True)` would otherwise leak.
    """

    name: str = ""

    @cached_property
    def command(self) -> BaseCommand:
        """The resolved local command, looked up lazily so importing doesn't require it."""
        return local[self.name]

    @staticmethod
    def foreground(command: BaseCommand) -> bool:
        """Run ``command`` attached to the terminal, returning whether it succeeded."""
        return bool(command & TF(FG=True))

    @staticmethod
    def passthrough(command: BaseCommand) -> int:
        """Run ``command`` attached to the terminal, returning its exact exit code.

        Unlike :meth:`foreground` (a success bool), this preserves the code so a
        transparent ``chefe run`` exits with whatever the wrapped command exited
        — the difference between a failed task reporting failure and reporting ``0``.
        """
        try:
            command & FG
        except ProcessExecutionError as error:
            return error.retcode if isinstance(error.retcode, int) else 1
        return 0

    def scope(self) -> tuple[str, ...]:
        """Args injected after the verb to pin the command to this workspace (default none)."""
        return ()

    def available(self) -> bool:
        """Whether the command should run at all (e.g. npm needs a `package.json`)."""
        return True

    def cwd(self) -> Path | None:
        """Directory to run in, for tools that target a workspace by location, not a flag."""
        return None

    @staticmethod
    def flags(**options: bool | str | None) -> tuple[str, ...]:
        """Turn keyword options into CLI args (`_`→`-`); drop `False`/`None`/`""`.

        A `True` becomes a bare `--flag`; any other value becomes `--flag value`.
        """
        out: list[str] = []
        for key, value in options.items():
            if value is None or value is False or value == "":
                continue
            out.append(f"--{key.replace('_', '-')}")
            if value is not True:
                out.append(str(value))
        return tuple(out)

    def __call__(self, verb: str, *args: str, **flags: bool | str | None) -> bool:
        """Run the backend in the foreground, returning success; a no-op if unavailable.

        Keyword ``flags`` translate to CLI args (`pypi=True` → `--pypi`, `feature=env` →
        `--feature env`), inserted before the positional ``args``.
        """
        if not self.available():
            return True
        return self.within_cwd(lambda command: self.foreground(command), verb, *args, **flags)

    def exit_code(self, verb: str, *args: str, **flags: bool | str | None) -> int:
        """Run in the foreground and return the command's exact exit code (``0`` if unavailable).

        The code-preserving sibling of :meth:`__call__`, for ``chefe run``'s transparent
        passthrough where a failing command must exit non-zero.
        """
        if not self.available():
            return 0
        return self.within_cwd(lambda command: self.passthrough(command), verb, *args, **flags)

    def within_cwd(
        self,
        action: Callable[[BaseCommand], T],
        verb: str,
        *args: str,
        **flags: bool | str | None,
    ) -> T:
        """Build ``verb + scope + flags + args`` and run ``action`` on it inside ``cwd``."""
        command = self.command[(verb, *self.scope(), *self.flags(**flags), *args)]
        directory = self.cwd()
        if directory is None:
            return action(command)
        with local.cwd(str(directory)):
            return action(command)

    def installed(self, env: str) -> dict[str, Installed]:
        """Packages currently provisioned for ``env``: name -> :class:`Installed`."""
        raise NotImplementedError
