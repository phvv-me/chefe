from collections.abc import Callable
from pathlib import Path
from typing import Annotated

from cyclopts import Parameter
from rich.console import Console

from ..backends import PixiGlobal
from ..core import ChefeError
from ..manifest import Manifest, Spec
from ..report import markup

# `chefe global add -l <lang>` aliases: the runtime name a user types, and the ecosystem name
# of the backend it routes to. Both the runtime (`nodejs`) and the ecosystem (`npm`) resolve here.
_LANGUAGES = {
    "conda": "conda",
    "python": "pypi",
    "pypi": "pypi",
    "pip": "pypi",
    "nodejs": "npm",
    "npm": "npm",
    "rust": "cargo",
    "cargo": "cargo",
}

# The conda runtime each non-conda ecosystem needs, since pip/npm/cargo run from inside the
# global env, so a fresh env installs this first (`chefe global add codex -l nodejs` just works).
_RUNTIMES = {"pypi": "python", "npm": "nodejs", "cargo": "rust"}


class GlobalEnv:
    """The shared global pixi env: declared deps installed once, reused across workspaces.

    Conda goes through `pixi global`; Python, Node.js, and Rust then install with the global
    env's own pip/npm/cargo, so a runtime add into a fresh env first provisions the matching
    runtime. Bound once to the pixi backend and the manifest loader, it owns the whole
    `chefe global ...` command surface.
    """

    def __init__(self, pixi: PixiGlobal, load: Callable[[], Manifest], console: Console) -> None:
        self.pixi = pixi
        self.load = load
        self.console = console

    @staticmethod
    def ecosystem(language: str) -> str:
        """Resolve a user's `-l` value to the ecosystem backend, rejecting unknown names."""
        if (ecosystem := _LANGUAGES.get(language)) is None:
            choices = ", ".join(dict.fromkeys(_LANGUAGES))
            raise ChefeError(f"Unknown language `{language}`. Choose one of: {choices}.")
        return ecosystem

    @staticmethod
    def pinned(pkg: str, dep: Spec) -> str:
        """An npm spec string for ``pkg`` at ``dep``'s version, in the form npm expects."""
        return pkg if dep.version in (None, "*") else f"{pkg}@{dep.version}"

    @staticmethod
    def spec(pkg: str, dep: Spec) -> str:
        """A conda spec string for ``pkg`` at ``dep``'s version, in the form pixi expects."""
        version = dep.version
        if version is None or version == "*":
            return pkg
        # A bare pin like "3.11" needs an operator, or it reads as part of the name.
        return f"{pkg}{version}" if version[0] in "<>=!~" else f"{pkg}=={version}"

    def add(
        self,
        *packages: str,
        language: Annotated[
            str,
            Parameter(
                name=("--language", "-l"),
                help="conda (default), python/pypi, nodejs/npm, or rust/cargo.",
            ),
        ] = "conda",
        env: Annotated[
            str,
            Parameter(
                name=("--environment", "-e"),
                help="Global environment to mutate; defaults to workspace.name.",
            ),
        ] = "",
    ) -> None:
        """Add packages to a shared global pixi env, routed by ``language`` to its backend.

        conda goes straight to `pixi global` (creating the env on demand), while python, nodejs,
        and rust install with the env's own pip/npm/cargo. Those run from inside the env, so a
        runtime add into a fresh env first provisions the matching runtime, which makes
        `chefe global add codex -l nodejs` a one-step command on a clean machine.
        """
        if not packages:
            raise ChefeError(
                "No packages given. Usage: `chefe global add <package> [-l language]`."
            )
        ecosystem = self.ecosystem(language)
        name = env or self.load().workspace.name
        if ecosystem == "conda":
            self.pixi.add(name, packages)
        else:
            backend = {"pypi": self.pixi.pip, "npm": self.pixi.npm}.get(ecosystem, self.pixi.cargo)
            backend(self.ensure(name, ecosystem=ecosystem), list(packages))
        self.console.print(
            markup(t"[green]added[/green] {', '.join(packages)} to [bold]{name}[/bold]")
        )

    def ensure(self, name: str, *, ecosystem: str) -> Path:
        """Global env prefix for ``name``, provisioning its runtime on demand for a runtime add.

        pip/npm/cargo run from inside the env, so the env must already own the matching runtime. A
        missing env is created here with that runtime (`pixi global install python|nodejs|rust`)
        before the package install, so a runtime add is a single command rather than a forced
        `chefe global install` first.
        """
        if not self.pixi.exists(name):
            runtime = _RUNTIMES[ecosystem]
            self.console.print(
                markup(t"[cyan]provisioning[/cyan] global env [bold]{name}[/bold] with {runtime}")
            )
            self.pixi.install(name, [runtime])
        return self.pixi.prefix(name)

    def install(self, name: str = "") -> None:
        """Install every language/toolchain's declared deps into one shared global pixi env.

        Conda goes through `pixi global`; adapters then use binaries from that global env for
        languages that need a second install step, such as Python, Node.js, and Rust.
        """
        manifest = self.load()
        name = name or manifest.workspace.name
        toolchains = manifest.toolchains()
        self.pixi.install(name, [self.spec(pkg, dep) for pkg, dep in manifest.deps.items()])

        prefix = self.pixi.prefix(name)
        if (python := toolchains.get("python")) and python.all_deps():
            self.pixi.pip(prefix, [self.spec(p, d) for p, d in python.all_deps().items()])
        if (nodejs := toolchains.get("nodejs")) and nodejs.all_deps():
            self.pixi.npm(prefix, [self.pinned(p, d) for p, d in nodejs.all_deps().items()])
        if (rust := toolchains.get("rust")) and rust.all_deps():
            self.pixi.cargo(prefix, list(rust.all_deps()))

        total = sum(
            len(group)
            for group in (
                manifest.deps,
                *(toolchain.all_deps() for toolchain in toolchains.values()),
            )
        )
        self.console.print(
            markup(t"[green]installed[/green] {total} deps into [bold]{name}[/bold]")
        )

    def list(
        self,
        regex: str = "",
        env: Annotated[
            str,
            Parameter(name=("--environment", "-e"), help="Show packages inside one global env."),
        ] = "",
        *,
        json: bool = False,
        sort_by: str = "",
    ) -> None:
        """Show installed global envs, or packages inside one global env."""
        self.pixi.show(env, regex=regex, json=json, sort_by=sort_by)

    def remove(
        self,
        *packages: str,
        env: Annotated[
            str,
            Parameter(
                name=("--environment", "-e"),
                help="Global environment to mutate; defaults to workspace.name.",
            ),
        ] = "",
    ) -> None:
        """Remove conda packages from a shared global pixi env."""
        if not packages:
            raise ChefeError("No packages given. Usage: `chefe global remove <package>...`.")
        name = env or self.load().workspace.name
        self.pixi.remove(name, packages)
        self.console.print(
            markup(t"[green]removed[/green] {', '.join(packages)} from [bold]{name}[/bold]")
        )
