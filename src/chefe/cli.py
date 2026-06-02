from __future__ import annotations

from cyclopts import App

from . import NAME
from .manager import PackageManager


def build(manager: PackageManager) -> App:
    """Wire ``manager``'s commands into a cyclopts app (bound methods register directly)."""
    app = App(name=NAME, help="One manifest, many package managers.")
    glob = App(name="global", help="Install the conda deps into the shared global pixi env.")
    app.command(glob)
    for method in (
        manager.init,
        manager.sync,
        manager.install,
        manager.update,
        manager.clean,
        manager.run,
        manager.shell,
        manager.tree,
        manager.add,
        manager.upgrade,
        manager.remove,
    ):
        app.command(method)
    glob.command(manager.global_install, name="install")
    return app


app = build(PackageManager())


if __name__ == "__main__":
    app()
