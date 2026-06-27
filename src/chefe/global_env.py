from collections.abc import Callable
from pathlib import Path
from typing import Annotated

from cyclopts import Parameter
from rich.console import Console

from . import GLOBAL_LANGUAGES, GLOBAL_RUNTIMES
from .backends import Pixi
from .console import markup
from .errors import ChefeError
from .manifest import Manifest, Spec


class GlobalEnv:
    """The shared global pixi env: declared deps installed once, reused across workspaces.

    Conda goes through `pixi global`; Python, Node.js, and Rust then install with the global
    env's own pip/npm/cargo, so a runtime add into a fresh env first provisions the matching
    runtime. Bound once to the pixi backend and the manifest loader, it owns the whole
    `chefe global ...` command surface.
    """

    def __init__(self, pixi: Pixi, load: Callable[[], Manifest], console: Console) -> None:
        self.pixi = pixi
        self.load = load
        self.console = console

    def install(self, name: str = "") -> None:
        """Install every language/toolchain's declared deps into one shared global pixi env.

        Conda goes through `pixi global`; adapters then use binaries from that global env for
        languages that need a second install step, such as Python, Node.js, and Rust.
        """
        manifest = self.load()
        name = name or manifest.workspace.name
        toolchains = manifest.toolchains()
        self.pixi.global_install(name, [self.spec(pkg, dep) for pkg, dep in manifest.deps.items()])

        prefix = self.pixi.global_prefix(name)
        if (python := toolchains.get("python")) and python.all_deps():
            self.pixi.global_pip(prefix, [self.spec(p, d) for p, d in python.all_deps().items()])
        if (nodejs := toolchains.get("nodejs")) and nodejs.all_deps():
            self.pixi.global_npm(
                prefix,
                [
                    p if d.version in (None, "*") else f"{p}@{d.version}"
                    for p, d in nodejs.all_deps().items()
                ],
            )
        if (rust := toolchains.get("rust")) and rust.all_deps():
            self.pixi.global_cargo(prefix, list(rust.all_deps()))

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
            self.pixi.global_add(name, packages)
        else:
            backend = {"pypi": self.pixi.global_pip, "npm": self.pixi.global_npm}.get(
                ecosystem, self.pixi.global_cargo
            )
            backend(self.ensure(name, ecosystem), list(packages))
        self.console.print(
            markup(t"[green]added[/green] {', '.join(packages)} to [bold]{name}[/bold]")
        )

    @staticmethod
    def ecosystem(language: str) -> str:
        """Resolve a user's `-l` value to the ecosystem backend, rejecting unknown names."""
        if (ecosystem := GLOBAL_LANGUAGES.get(language)) is None:
            choices = ", ".join(dict.fromkeys(GLOBAL_LANGUAGES))
            raise ChefeError(f"Unknown language `{language}`. Choose one of: {choices}.")
        return ecosystem

    def ensure(self, name: str, ecosystem: str) -> Path:
        """Global env prefix for ``name``, provisioning its runtime on demand for a runtime add.

        pip/npm/cargo run from inside the env, so the env must already own the matching runtime. A
        missing env is created here with that runtime (`pixi global install python|nodejs|rust`)
        before the package install, so a runtime add is a single command rather than a forced
        `chefe global install` first.
        """
        if not self.pixi.global_exists(name):
            runtime = GLOBAL_RUNTIMES[ecosystem]
            self.console.print(
                markup(t"[cyan]provisioning[/cyan] global env [bold]{name}[/bold] with {runtime}")
            )
            self.pixi.global_install(name, [runtime])
        return self.pixi.global_prefix(name)

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
        self.pixi.global_remove(name, packages)
        self.console.print(
            markup(t"[green]removed[/green] {', '.join(packages)} from [bold]{name}[/bold]")
        )

    def list(
        self,
        regex: str = "",
        env: Annotated[
            str,
            Parameter(name=("--environment", "-e"), help="Show packages inside one global env."),
        ] = "",
        json: bool = False,
        sort_by: str = "",
    ) -> None:
        """Show installed global envs, or packages inside one global env."""
        self.pixi.global_list(env, regex, json, sort_by)
