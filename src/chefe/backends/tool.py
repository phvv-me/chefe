import codecs
import sys
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from functools import cached_property
from pathlib import Path
from subprocess import PIPE
from typing import NamedTuple, Protocol, TextIO, cast

from plumbum import local
from plumbum.commands.base import BaseCommand

from ..errors import ChefeError
from ..state import Installed


class CommandResult(NamedTuple):
    """One completed backend command with output retained for failure reporting."""

    returncode: int
    stdout: str
    stderr: str

    @property
    def succeeded(self) -> bool:
        """Whether the command exited cleanly."""
        return self.returncode == 0

    def replay(self) -> None:
        """Write retained output to the caller's streams and flush it immediately."""
        sys.stdout.write(self.stdout)
        sys.stdout.flush()
        sys.stderr.write(self.stderr)
        sys.stderr.flush()


class ChunkStream(Protocol):
    """A binary pipe that returns the bytes currently available without filling the request."""

    def read1(self, size: int = -1, /) -> bytes:
        """Read at most ``size`` bytes with one call to the underlying pipe."""
        ...


class Tool:
    """A package-manager backend: call it to run a foreground command, query what's installed.

    Subclasses set ``name`` and override ``scope`` (args that pin the command to the workspace)
    and ``available`` (a guard). ``installed`` is theirs to implement per ecosystem.

    plumbum is untyped, so this class is the single seam that touches it. Every foreground run
    funnels through ``stream``, which tees output to the caller and retains a typed copy for
    diagnostics instead of trusting an inherited batch-job file descriptor.
    """

    name: str = ""

    @cached_property
    def command(self) -> BaseCommand:
        """The resolved local command, looked up lazily so importing doesn't require it."""
        return local[self.name]

    @staticmethod
    def foreground(command: BaseCommand) -> bool:
        """Run ``command`` attached to the terminal, returning whether it succeeded."""
        return Tool.stream(command).succeeded

    @staticmethod
    def stream(command: BaseCommand) -> CommandResult:
        """Run ``command`` while teeing and retaining both output streams."""
        process = command.popen(stdin=None, stdout=PIPE, stderr=PIPE)
        assert process.stdout is not None and process.stderr is not None
        stdout_pipe = cast(ChunkStream, process.stdout)
        stderr_pipe = cast(ChunkStream, process.stderr)
        encoding = sys.getfilesystemencoding()
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="chefe-output") as executor:
            stdout = executor.submit(Tool._relay, stdout_pipe, sys.stdout, encoding)
            stderr = executor.submit(Tool._relay, stderr_pipe, sys.stderr, encoding)
            returncode = process.wait()
        return CommandResult(returncode, stdout.result(), stderr.result())

    @staticmethod
    def _relay(stream: ChunkStream, destination: TextIO, encoding: str) -> str:
        """Copy available pipe bytes to ``destination`` while retaining decoded text.

        ``BufferedReader.read(size)`` may wait for all ``size`` bytes while a long-lived child
        remains open. ``read1`` returns after one underlying pipe read instead, so short protocol
        messages such as MCP JSON responses reach their client immediately.
        """
        decoder = codecs.getincrementaldecoder(encoding)(errors="replace")
        chunks: list[str] = []
        while chunk := stream.read1(4096):
            text = decoder.decode(chunk)
            chunks.append(text)
            destination.write(text)
            destination.flush()
        if tail := decoder.decode(b"", final=True):
            chunks.append(tail)
            destination.write(tail)
            destination.flush()
        return "".join(chunks)

    def output(self, command: BaseCommand, operation: str) -> str:
        """Capture a query command, replaying its output before a user-facing failure."""
        returncode, stdout, stderr = command.run(retcode=None)
        result = CommandResult(int(returncode), str(stdout), str(stderr))
        if not result.succeeded:
            result.replay()
            raise ChefeError(f"`{operation}` failed (see its output above)")
        return result.stdout

    @staticmethod
    def passthrough(command: BaseCommand) -> int:
        """Run ``command`` attached to the terminal, returning its exact exit code.

        Unlike :meth:`foreground` (a success bool), this preserves the code so a
        transparent ``chefe run`` exits with whatever the wrapped command exited
        instead of collapsing every failure to ``1``.
        """
        return Tool.stream(command).returncode

    @staticmethod
    def handover(command: BaseCommand) -> int:
        """Give ``command`` the caller's own terminal on all three streams, returning its code.

        An interactive program draws its own screen: a shell, a REPL or a pager puts the terminal
        into raw mode and expects every keystroke and every escape sequence to travel over the
        tty. :meth:`stream` gives it pipes instead so it can retain a copy of the output, which
        leaves such a program typing into a terminal nothing ever redraws. Those callers come
        here and trade the retained copy for a working terminal.
        """
        return command.popen(stdin=None, stdout=None, stderr=None).wait()

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

    def __call__(self, verb: str, *args: str, **flags: bool | str | None) -> None:
        """Run the backend in the foreground; a no-op if unavailable, `ChefeError` on failure.

        Keyword ``flags`` translate to CLI args (`pypi=True` → `--pypi`, `feature=env` →
        `--feature env`), inserted before the positional ``args``. Raising on failure keeps
        a failed solve or install from being reported as green success by the caller.
        """
        if not self.available():
            return
        if not self.within_cwd(self.foreground, verb, *args, **flags):
            raise ChefeError(f"`{self.name} {verb}` failed (see its output above)")

    def exit_code(self, verb: str, *args: str, **flags: bool | str | None) -> int:
        """Run in the foreground and return the command's exact exit code (``0`` if unavailable).

        The code-preserving sibling of :meth:`__call__`, for ``chefe run``'s transparent
        passthrough where a failing command must exit non-zero.
        """
        if not self.available():
            return 0
        return self.within_cwd(lambda command: self.passthrough(command), verb, *args, **flags)

    def within_cwd[T](
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
