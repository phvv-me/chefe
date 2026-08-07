from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Annotated

from cyclopts import Parameter
from rich.console import Console

from ..backends import PixiGlobal
from ..core import ChefeError
from ..manifest import Manifest, Spec, ToolchainSpec
from ..report import markup
from .stage import SecondStage

# Both the familiar runtime name (`nodejs`) and its exact ecosystem name (`npm`) resolve to the
# same value, so either spelling routes to the same backend; the values double as `_RUNTIMES`'
# keys below.
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

        Conda goes through `pixi global` first, since every second-stage runtime is itself a conda
        package, then each toolchain in `_second_stages` installs its own deps with the env's own
        pip/npm/cargo. A toolchain the manifest never declares, or declares without deps, is
        skipped rather than provisioned empty.
        """
        manifest = self.load()
        name = name or manifest.workspace.name
        toolchains = manifest.toolchains()

        self.pixi.install(name, self._spec_list(manifest.deps))
        prefix = self.pixi.prefix(name)
        for stage in self._second_stages():
            if (declared := toolchains.get(stage.toolchain)) and declared.all_deps():
                stage.install(prefix, stage.specs(declared.all_deps()))

        self.console.print(self._install_summary(name, manifest.deps, toolchains))

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

    def show(
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

    def _crate_list(self, deps: Mapping[str, Spec]) -> list[str]:
        """Crate names for `deps`, since a global `cargo install` carries no version pin."""
        return list(deps)

    def _install_summary(
        self, name: str, deps: Mapping[str, Spec], toolchains: Mapping[str, ToolchainSpec]
    ) -> str:
        """Markup reporting how many deps, across conda plus every toolchain, went into `name`."""
        total = sum(
            len(group)
            for group in (deps, *(toolchain.all_deps() for toolchain in toolchains.values()))
        )
        return markup(t"[green]installed[/green] {total} deps into [bold]{name}[/bold]")

    def _pinned_list(self, deps: Mapping[str, Spec]) -> list[str]:
        """npm-style spec strings for `deps`, in the form `npm install -g` expects."""
        return [self.pinned(pkg, dep) for pkg, dep in deps.items()]

    def _second_stages(self) -> tuple[SecondStage, ...]:
        """Every toolchain chefe installs after conda, in the order they must install in.

        Conda provides each of these runtimes, so all of them run after it, and the declared order
        here is the install order. A new toolchain joins by adding its `PixiGlobal` installer and
        one entry below, rather than by editing `install`.
        """
        return (
            SecondStage("python", self.pixi.pip, self._spec_list),
            SecondStage("nodejs", self.pixi.npm, self._pinned_list),
            SecondStage("rust", self.pixi.cargo, self._crate_list),
        )

    def _spec_list(self, deps: Mapping[str, Spec]) -> list[str]:
        """Conda-style spec strings for `deps`, in the form `pixi global install` expects."""
        return [self.spec(pkg, dep) for pkg, dep in deps.items()]
