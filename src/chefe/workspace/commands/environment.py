import shutil
from pathlib import Path
from typing import Annotated

from cyclopts import Parameter
from rich.console import Console

from ...backends import Pixi
from ...core import current_platform
from ...report import markup
from ..compiler import Compiler
from ..generated import ActivationScript
from ..layout import Workspace
from ..runtime import Runtime

_ACTIVATE = "activate.sh"


class EnvironmentCommands:
    """`chefe init|sync|install|activate|update|clean`: the life of a workspace's environment.

    Each method is one command as a user types it, so the body reads as the steps that command
    performs and every step is a call into the collaborator that owns it.
    """

    def __init__(
        self,
        workspace: Workspace,
        compiler: Compiler,
        runtime: Runtime,
        pixi: Pixi,
        console: Console,
    ) -> None:
        self.workspace = workspace
        self.compiler = compiler
        self.runtime = runtime
        self.pixi = pixi
        self.console = console

    def activate(self, env: str = "default") -> Path:
        """Generate `.chefe/activate.sh` for this host and return its path.

        Writes the manifest's `[modules]` `name = version` pairs as `module purge` + `module
        load name/version ...` (guarded so it no-ops off a cluster), followed by the pixi
        activation, so a job or interactive shell can `source .chefe/activate.sh && python -m ...`.
        """
        self.workspace.out.mkdir(exist_ok=True)
        path = self.workspace.out / _ACTIVATE
        modules = self.workspace.load().modules.specs()
        ActivationScript(path, self.pixi.shell_hook(env)).write(modules)
        chosen = ", ".join(modules) if modules else "pixi env only (no modules)"
        self.console.print(markup(t"[green]wrote[/green] {path} · modules: [bold]{chosen}[/bold]"))
        return path

    def clean(self) -> None:
        """Remove the generated env and manifests."""
        shutil.rmtree(self.workspace.out, ignore_errors=True)
        self.console.print(f"[green]removed[/green] {self.workspace.out.name}/")

    def init(self, name: str = "") -> None:
        """Scaffold a starter manifest."""
        manifest = self.workspace.manifest
        if manifest.exists():
            self.console.print(f"[yellow]{manifest.name} already exists[/yellow], untouched")
            return
        name = name or Path.cwd().name
        manifest.write_text(
            f'[workspace]\nname = "{name}"\nversion = "0.1.0"\n'
            f'platforms = ["{current_platform()}"]\n'
            'channels = ["conda-forge"]\n\n[deps]\npython = ">=3.11"\n'
        )
        self.console.print(
            markup(t"[green]created[/green] {manifest.name} for [bold]{name}[/bold]")
        )

    def install(
        self,
        env: str = "default",
        *,
        activate_only: Annotated[bool, Parameter(name="--activate-only")] = False,
        resolve: Annotated[bool, Parameter(name="--resolve")] = False,
    ) -> None:
        """Sync, then make ``env`` match the manifest across every language/toolchain.

        Always (re)generates the per-host `activate.sh` so a job or interactive shell can
        `source .chefe/activate.sh && python -m ...`. `--activate-only` skips the package
        install and just refreshes that script against the already-provisioned env. An existing
        lock is required by default. `--resolve` explicitly permits updating it on this machine.
        """
        if not activate_only:
            self.runtime.provision(env, resolve=resolve)
            self.console.print(markup(t"[green]installed[/green] env [bold]{env}[/bold]"))
        self.activate(env)

    def sync(self, env: str = "default") -> None:
        """Compile the manifest into the generated `{pixi.toml, package.json}` for ``env``."""
        self.compiler.sync(env)

    def update(self, env: str = "default") -> None:
        """Re-solve to the newest allowed versions across ecosystems."""
        self.runtime.update_all(env)
        self.console.print(markup(t"[green]updated[/green] env [bold]{env}[/bold]"))
