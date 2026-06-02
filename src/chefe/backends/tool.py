from __future__ import annotations

from functools import cached_property

from plumbum import TF, local
from plumbum.commands.base import BaseCommand

from ..state import Installed


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

    def scope(self) -> tuple[str, ...]:
        """Args injected after the verb to pin the command to this workspace (default none)."""
        return ()

    def available(self) -> bool:
        """Whether the command should run at all (e.g. npm needs a `package.json`)."""
        return True

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
        argv = (verb, *self.scope(), *self.flags(**flags), *args)
        return self.foreground(self.command[argv])

    def installed(self, env: str) -> dict[str, Installed]:
        """Packages currently provisioned for ``env``: name -> :class:`Installed`."""
        raise NotImplementedError
