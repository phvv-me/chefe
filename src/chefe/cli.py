import functools
import os
from collections.abc import Callable
from pathlib import Path
from typing import Literal, Protocol

from cyclopts import App

from . import NAME
from .console import markup
from .errors import ChefeError
from .manager import PackageManager

# Shells cyclopts can emit a completion script for; the value chefe defaults to when a
# user passes none is read from their login `$SHELL`.
Shell = Literal["bash", "zsh", "fish"]
SHELLS: tuple[Shell, ...] = ("bash", "zsh", "fish")

# The flags cyclopts would normally intercept as its own help request. `run` disables that
# interception (it registers with `help_flags=()`) and forwards them like any passthrough
# flag, so these are the tokens `run_command` itself must recognize as asking about `run`.
HELP_FLAGS = ("--help", "-h")


def handled[**P, R](manager: PackageManager, method: Callable[P, R]) -> Callable[P, R]:
    """Wrap a command so Chefe's own errors print cleanly instead of tracebacking."""

    @functools.wraps(method)
    def run(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return method(*args, **kwargs)
        except ChefeError as error:
            manager.console.print(markup(t"[red]error[/red]: {error}"))
            raise SystemExit(1) from None

    return run


def detect_shell(shell: Shell | None) -> Shell:
    """The completion shell to target: an explicit choice, else the basename of `$SHELL`.

    Falls back to bash when `$SHELL` names something cyclopts cannot emit (a login shell of
    `dash` or an unset variable), so `chefe completions` always prints a usable script.
    """
    if shell is not None:
        return shell
    name = Path(os.environ.get("SHELL", "")).name
    return next((candidate for candidate in SHELLS if candidate == name), "bash")


def completions_command(app: App) -> Callable[[Shell | None], None]:
    """A `completions` command that prints ``app``'s shell-completion script to stdout.

    Closing over the built ``app`` keeps the manager free of cyclopts internals: the script is
    pure CLI surface. Printing (rather than installing) lets a user pipe it where their shell
    expects, e.g. `chefe completions zsh > ~/.zfunc/_chefe` or `eval "$(chefe completions)"`.
    """

    def completions(shell: Shell | None = None) -> None:
        """Print the shell-completion script for ``shell`` (default: your `$SHELL`)."""
        print(app.generate_completion(prog_name=NAME, shell=detect_shell(shell)), end="")

    return completions


class RunCommand(Protocol):
    """The registered `run` surface: the whole command line as one var-positional."""

    def __call__(self, *argv: str) -> None: ...


def run_command(manager: PackageManager, app: App) -> RunCommand:
    """A `run` command that hands help flags to the target instead of to cyclopts.

    cyclopts intercepts its help flags anywhere in a command's tokens, so `chefe run atpx
    --help` printed chefe run's own usage and the flag never reached atpx. The command
    therefore registers with `help_flags=()` and handles help itself. A help flag after a
    task or executable name passes through verbatim like any other flag, while a help flag
    in place of a name (only the optional leading `--env <name>`/`-e <name>` may precede
    it) asks about `run` itself, so the command's own page prints through the built
    ``app``, the same closure idiom as `completions`.
    """
    command = handled(manager, manager.run)

    @functools.wraps(command)
    def run(*argv: str) -> None:
        target = argv[2:] if argv[:1] in (("--env",), ("-e",)) else argv
        if target and target[0] in HELP_FLAGS:
            app.help_print(["run"])
            return
        command(*argv)

    return run


def build(manager: PackageManager) -> App:
    """Wire ``manager``'s commands into a cyclopts app (bound methods register directly).

    Each method is wrapped by `handled` at its own call site so the type checker
    sees one concrete signature per command, rather than the heterogeneous union of
    every method shape that a loop over a tuple would produce (which is unassignable
    to `handled`'s `Callable[P, R]`).
    """
    # cyclopts checks its auto `--version` flag eagerly against the whole argv, not just the
    # tokens meant for the app itself, so a bare `--version` anywhere inside `run`'s or `x`'s
    # `Parameter(allow_leading_hyphen=True)` passthrough (e.g. `chefe run python --version`)
    # never reaches the wrapped command: it short-circuits to print chefe's own version instead
    # of the tool's. Passthrough correctness matters far more than a `chefe --version` nicety,
    # so the auto flag is off; chefe's own version is one `pip show chefe` away.
    app = App(name=NAME, help="One manifest, many package managers.", version_flags=[])
    glob = App(name="global", help="Install the conda deps into the shared global pixi env.")
    app.command(glob)
    app.command(handled(manager, manager.init))
    app.command(handled(manager, manager.sync))
    app.command(handled(manager, manager.install))
    app.command(handled(manager, manager.activate))
    app.command(handled(manager, manager.update))
    app.command(handled(manager, manager.clean))
    # Help flags get the same eager interception as the version check above, so `run`
    # registers without any and forwards them itself; see `run_command`.
    app.command(run_command(manager, app), help_flags=())
    # `x` is the short verb; `exec` is the alias for people who reach for the longer name.
    app.command(handled(manager, manager.x), name=("x", "exec"))
    app.command(handled(manager, manager.shell))
    app.command(handled(manager, manager.tree))
    app.command(handled(manager, manager.add))
    app.command(handled(manager, manager.upgrade))
    app.command(handled(manager, manager.remove))
    glob.command(handled(manager, manager.glob.install), name="install")
    glob.command(handled(manager, manager.glob.add), name="add")
    glob.command(handled(manager, manager.glob.remove), name="remove")
    glob.command(handled(manager, manager.glob.list), name="list")
    app.command(completions_command(app), name="completions")
    return app


app = build(PackageManager())


if __name__ == "__main__":
    app()
