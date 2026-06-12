import functools
from collections.abc import Callable

from cyclopts import App

from . import NAME
from .console import markup
from .errors import ChefeError
from .manager import PackageManager


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


def build(manager: PackageManager) -> App:
    """Wire ``manager``'s commands into a cyclopts app (bound methods register directly).

    Each method is wrapped by `handled` at its own call site so the type checker
    sees one concrete signature per command, rather than the heterogeneous union of
    every method shape that a loop over a tuple would produce (which is unassignable
    to `handled`'s `Callable[P, R]`).
    """
    app = App(name=NAME, help="One manifest, many package managers.")
    glob = App(name="global", help="Install the conda deps into the shared global pixi env.")
    app.command(glob)
    app.command(handled(manager, manager.init))
    app.command(handled(manager, manager.sync))
    app.command(handled(manager, manager.install))
    app.command(handled(manager, manager.activate))
    app.command(handled(manager, manager.update))
    app.command(handled(manager, manager.clean))
    app.command(handled(manager, manager.run))
    app.command(handled(manager, manager.x))
    app.command(handled(manager, manager.shell))
    app.command(handled(manager, manager.tree))
    app.command(handled(manager, manager.add))
    app.command(handled(manager, manager.upgrade))
    app.command(handled(manager, manager.remove))
    glob.command(handled(manager, manager.global_install), name="install")
    glob.command(handled(manager, manager.global_add), name="add")
    glob.command(handled(manager, manager.global_remove), name="remove")
    glob.command(handled(manager, manager.global_list), name="list")
    return app


app = build(PackageManager())


if __name__ == "__main__":
    app()
