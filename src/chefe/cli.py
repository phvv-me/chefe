import functools
from collections.abc import Callable
from typing import Any

from cyclopts import App
from rich.markup import escape

from . import NAME
from .errors import ChefeError
from .manager import PackageManager

Command = Callable[..., Any]


def handled(manager: PackageManager, method: Command) -> Command:
    """Wrap a command so Chefe's own errors print cleanly instead of tracebacking."""

    @functools.wraps(method)
    def run(*args: Any, **kwargs: Any) -> Any:
        try:
            return method(*args, **kwargs)
        except ChefeError as error:
            manager.console.print(f"[red]error[/red]: {escape(str(error))}")
            raise SystemExit(1) from None

    return run


def build(manager: PackageManager) -> App:
    """Wire ``manager``'s commands into a cyclopts app (bound methods register directly)."""
    app = App(name=NAME, help="One manifest, many package managers.")
    glob = App(name="global", help="Install the conda deps into the shared global pixi env.")
    app.command(glob)
    for method in (
        manager.init,
        manager.sync,
        manager.install,
        manager.activate,
        manager.update,
        manager.clean,
        manager.run,
        manager.x,
        manager.shell,
        manager.tree,
        manager.add,
        manager.upgrade,
        manager.remove,
    ):
        app.command(handled(manager, method))
    glob.command(handled(manager, manager.global_install), name="install")
    return app


app = build(PackageManager())


if __name__ == "__main__":
    app()
