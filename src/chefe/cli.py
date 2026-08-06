import functools
import os
from collections.abc import Callable
from pathlib import Path
from typing import Literal, NoReturn, Protocol

from cyclopts import App
from rich.console import Console

from .core import ChefeError, Project
from .manager import PackageManager
from .report import markup

# Shells cyclopts can emit a completion script for; the value chefe defaults to when a
# user passes none is read from their login `$SHELL`.
Shell = Literal["bash", "zsh", "fish"]
_SHELLS: tuple[Shell, ...] = ("bash", "zsh", "fish")

# The help flags cyclopts would intercept. `run` registers with `help_flags=()` and forwards
# them as passthrough, so `_run_command` has to recognize them itself.
_HELP_FLAGS = ("--help", "-h")


def _handled[**P, R](errors: Console, method: Callable[P, R]) -> Callable[P, R]:
    """Wrap a command so Chefe's own errors print cleanly to ``errors`` instead of tracebacking.

    The two halves of the contract are what a scripted caller depends on: the message goes to the
    failure channel, never to the stdout a CI step or an agent captures as the command's output,
    and the process exits non-zero so the flow stops instead of continuing against a workspace
    that was never provisioned. Taking the console rather than the whole manager keeps the wrapper
    dependent on the one thing it uses.
    """

    def stop(error: ChefeError) -> NoReturn:
        errors.print(markup(t"[red]error[/red]: {error}"))
        raise SystemExit(1) from None

    @functools.wraps(method)
    def run(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return method(*args, **kwargs)
        except ChefeError as error:
            stop(error)

    return run


def detect_shell(shell: Shell | None) -> Shell:
    """The completion shell to target: an explicit choice, else the basename of `$SHELL`.

    Falls back to bash when `$SHELL` names something cyclopts cannot emit (a login shell of
    `dash` or an unset variable), so `chefe completions` always prints a usable script.
    """
    if shell is not None:
        return shell
    name = Path(os.environ.get("SHELL", "")).name
    return next((candidate for candidate in _SHELLS if candidate == name), "bash")


def _completions_command(app: App) -> Callable[[Shell | None], None]:
    """A `completions` command that prints ``app``'s shell-completion script to stdout.

    Closing over the built ``app`` keeps the manager free of cyclopts internals: the script is
    pure CLI surface. Printing (rather than installing) lets a user pipe it where their shell
    expects, e.g. `chefe completions zsh > ~/.zfunc/_chefe` or `eval "$(chefe completions)"`.
    """

    def completions(shell: Shell | None = None) -> None:
        """Print the shell-completion script for ``shell`` (default: your `$SHELL`)."""
        print(app.generate_completion(prog_name=Project.name, shell=detect_shell(shell)), end="")

    return completions


class _RunCommand(Protocol):
    """The registered `run` surface: the whole command line as one var-positional."""

    def __call__(self, *argv: str) -> None: ...


def _run_command(manager: PackageManager, app: App) -> _RunCommand:
    """A `run` command that hands help flags to the target instead of to cyclopts.

    cyclopts intercepts its help flags anywhere in a command's tokens, so `chefe run atpx
    --help` printed chefe run's own usage and the flag never reached atpx. The command
    therefore registers with `help_flags=()` and handles help itself. A help flag after a
    task or executable name passes through verbatim like any other flag, while a help flag
    in place of a name (only the optional leading `--env <name>`/`-e <name>` may precede
    it) asks about `run` itself, so the command's own page prints through the built
    ``app``, the same closure idiom as `completions`.
    """
    command = _handled(manager.errors, manager.execution.run)

    @functools.wraps(command)
    def run(*argv: str) -> None:
        target = argv[1:] if argv[:1] == ("--resolve",) else argv
        target = target[2:] if target[:1] in (("--env",), ("-e",)) else target
        if target and target[0] in _HELP_FLAGS:
            app.help_print(["run"])
            return
        command(*argv)

    return run


def _register_environment(app: App, manager: PackageManager) -> None:
    """Register the commands that create, refresh, and tear down a workspace's environment."""
    errors, environment = manager.errors, manager.environment
    app.command(_handled(errors, environment.init))
    app.command(_handled(errors, environment.sync))
    app.command(_handled(errors, environment.install))
    app.command(_handled(errors, environment.activate))
    app.command(_handled(errors, environment.update))
    app.command(_handled(errors, environment.clean))


def _register_execution(app: App, manager: PackageManager) -> None:
    """Register the commands that run something inside (or beside) the environment."""
    errors, execution = manager.errors, manager.execution
    # Help flags get the same eager interception as `build`'s version check, so `run`
    # registers without any and forwards them itself; see `_run_command`.
    app.command(_run_command(manager, app), help_flags=())
    # `x` is the short verb; `exec` is the alias for people who reach for the longer name.
    app.command(_handled(errors, execution.x), name=("x", "exec"))
    app.command(_handled(errors, execution.shell))


def _register_dependencies(app: App, manager: PackageManager) -> None:
    """Register the commands that read and edit the manifest's declared dependencies."""
    errors, dependencies = manager.errors, manager.dependencies
    app.command(_handled(errors, dependencies.tree))
    app.command(_handled(errors, dependencies.add))
    app.command(_handled(errors, dependencies.upgrade))
    app.command(_handled(errors, dependencies.remove))


def _register_global(glob: App, manager: PackageManager) -> None:
    """Register the `global` subcommands, which act on the shared env rather than a workspace."""
    errors = manager.errors
    glob.command(_handled(errors, manager.glob.install), name="install")
    glob.command(_handled(errors, manager.glob.add), name="add")
    glob.command(_handled(errors, manager.glob.remove), name="remove")
    glob.command(_handled(errors, manager.glob.list), name="list")


def build(manager: PackageManager) -> App:
    """Wire ``manager``'s commands into a cyclopts app (bound methods register directly).

    Each method is wrapped by `_handled` at its own call site so the type checker
    sees one concrete signature per command, rather than the heterogeneous union of
    every method shape that a loop over a tuple would produce (which is unassignable
    to `_handled`'s `Callable[P, R]`). The registrations are grouped by what a command
    acts on, so the four helpers below name the whole command surface.

    The auto `--version` flag stays off because cyclopts checks it eagerly against the whole
    argv, so a bare `--version` inside `run`'s or `x`'s `allow_leading_hyphen` passthrough (say
    `chefe run python --version`) would short-circuit to chefe's own version instead of reaching
    the wrapped command. Passthrough correctness matters more than the nicety, and chefe's
    version is one `pip show chefe` away.
    """
    app = App(name=Project.name, help="One manifest, many package managers.", version_flags=[])
    glob = App(name="global", help="Install the conda deps into the shared global pixi env.")
    app.command(glob)
    _register_environment(app, manager)
    _register_execution(app, manager)
    _register_dependencies(app, manager)
    _register_global(glob, manager)
    app.command(_completions_command(app), name="completions")
    return app


app = build(PackageManager())


if __name__ == "__main__":
    app()
