import shutil
from collections import Counter
from pathlib import Path
from typing import Annotated

import tomlkit
from cyclopts import Parameter
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from . import ECOSYSTEMS, ENV_DIR, MANIFEST, NAME, PIXI_RESOLVED
from .backends import Cargo, Node, Pixi
from .compiled import PackageJson, PixiManifest
from .manifest import Document, Manifest, Spec
from .state import Declared
from .utils import current_platform, satisfied


class PackageManager:
    """A workspace: one manifest, compiled into a generated env and run by the real tools."""

    def __init__(self, root: Path = Path()) -> None:
        self.manifest = root / MANIFEST
        self.root = root
        self.out = root / ENV_DIR
        self.pixi = Pixi(self.out)
        self.cargo = Cargo(self.out, self.pixi)
        self.console = Console()

    def load(self) -> Manifest:
        """The validated manifest."""
        return Manifest.load(self.manifest)

    def node(self, manifest: Manifest) -> Node:
        """The JS backend for this manifest: the `[npm] manager` binary in its install dir.

        Tooling installs into the generated `.chefe/` env; an application (`[npm] app`) installs
        at the project root, where Vite resolves `node_modules`. Either way the backend just runs
        the named binary there, so any package manager works without code here.
        """
        directory = self.root if manifest.npm.app else self.out
        return Node(directory, manifest.npm.manager)

    def declared(self, env: str) -> dict[str, Declared]:
        """Every dep declared for ``env`` on this host."""
        return self.load().declared(env, current_platform())

    def init(self, name: str = "") -> None:
        """Scaffold a starter manifest."""
        if self.manifest.exists():
            self.console.print(f"[yellow]{self.manifest.name} already exists[/yellow], untouched")
            return
        name = name or Path.cwd().name
        self.manifest.write_text(
            f'[workspace]\nname = "{name}"\nversion = "0.1.0"\n'
            f'platforms = ["{current_platform()}"]\n'
            'channels = ["conda-forge"]\n\n[deps]\npython = ">=3.11"\n'
        )
        self.console.print(
            f"[green]created[/green] {self.manifest.name} for [bold]{escape(name)}[/bold]"
        )

    def sync(self) -> None:
        """Compile the manifest into the generated `{pixi.toml, package.json}`."""
        manifest = self.load()
        self.out.mkdir(exist_ok=True)
        self.pixi.manifest.write_text(PixiManifest.from_manifest(manifest).to_toml())
        if (package := PackageJson.from_manifest(manifest)) is not None:
            self.node(manifest).manifest.write_text(package.to_json())
        self.console.print(f"[green]synced[/green] {self.manifest.name} → {self.out.name}/")

    def install(self, env: str = "default") -> None:
        """Sync, then make ``env`` match the manifest across every ecosystem."""
        self.sync()
        self.pixi("install", "-e", env)
        with self.pixi.activated(env):
            self.node(self.load())("install")
        crates = {n: d.spec for n, d in self.declared(env).items() if d.source == "cargo"}
        self.cargo.sync(env, crates)
        self.console.print(f"[green]installed[/green] env [bold]{escape(env)}[/bold]")

    def update(self, env: str = "default") -> None:
        """Re-solve to the newest allowed versions across ecosystems."""
        self.sync()
        self.pixi("update", "-e", env)
        with self.pixi.activated(env):
            self.node(self.load())("update")
        self.console.print(f"[green]updated[/green] env [bold]{escape(env)}[/bold]")

    def clean(self) -> None:
        """Remove the generated env and manifests."""
        shutil.rmtree(self.out, ignore_errors=True)
        self.console.print(f"[green]removed[/green] {self.out.name}/")

    def global_install(self, name: str = "") -> None:
        """Install every ecosystem's declared deps into one shared global pixi env.

        conda goes through `pixi global`; the runtimes it pulls in (python/node/rust)
        then install the pypi/npm/cargo deps with that env's own pip/npm/cargo — so a
        global install reaches parity with `chefe install`, no uv involved.
        """
        manifest = self.load()
        name = name or manifest.workspace.name

        def spec(pkg: str, dep: Spec) -> str:
            return pkg if dep.version in (None, "*") else f"{pkg}{dep.version}"

        conda = dict(manifest.deps)
        for runtime, deps in (
            ("python", manifest.pypi.deps),
            ("nodejs", manifest.npm.deps),
            ("rust", manifest.cargo.deps),
        ):
            if deps:
                conda.setdefault(runtime, Spec())
        self.pixi.global_install(name, [spec(pkg, dep) for pkg, dep in conda.items()])

        prefix = self.pixi.global_prefix(name)
        if manifest.pypi.deps:
            self.pixi.global_pip(prefix, [spec(p, d) for p, d in manifest.pypi.deps.items()])
        if manifest.npm.deps:
            self.pixi.global_npm(
                prefix,
                [
                    p if d.version in (None, "*") else f"{p}@{d.version}"
                    for p, d in manifest.npm.deps.items()
                ],
            )
        if manifest.cargo.deps:
            self.pixi.global_cargo(prefix, list(manifest.cargo.deps))

        total = sum(
            len(group)
            for group in (
                manifest.deps,
                manifest.pypi.deps,
                manifest.npm.deps,
                manifest.cargo.deps,
            )
        )
        self.console.print(
            f"[green]installed[/green] {total} deps into [bold]{escape(name)}[/bold]"
        )

    def run(self, task: str, *args: Annotated[str, Parameter(allow_leading_hyphen=True)]) -> None:
        """Run a task inside the env."""
        self.pixi("run", task, *args)

    def x(
        self,
        *args: Annotated[str, Parameter(allow_leading_hyphen=True)],
        with_: tuple[str, ...] = (),
    ) -> None:
        """Run a command in a throwaway env, like uvx or pipx run; no manifest needed.

        args: the command and its arguments, e.g. `chefe x ruff check .`.
        with_: extra packages to make available, e.g. `--with build`.
        """
        self.pixi.exec(with_, args)

    def shell(self, env: str = "default") -> None:
        """Open an activated shell in ``env``."""
        self.pixi("shell", "-e", env)

    def add(
        self,
        *packages: str,
        pypi: bool = False,
        cargo: bool = False,
        npm: bool = False,
        gem: bool = False,
        env: str = "",
        spec: str = "*",
    ) -> None:
        """Add packages to the manifest, then sync; conda + pypi resolve through pixi.

        Conda is the default source; `--pypi`/`--cargo`/`--npm`/`--gem` pick another.
        """
        source = next(
            (s for s, on in zip(ECOSYSTEMS, (pypi, cargo, npm, gem), strict=True) if on), "conda"
        )
        if source in PIXI_RESOLVED:
            self.sync()
            self.pixi("add", *packages, pypi=source == "pypi", feature=env)
            self.pull()
        else:
            document = Document(self.manifest)
            document.add(source, env, packages, spec)
            document.save()
            self.sync()
        self.console.print(f"[green]added[/green] {escape(', '.join(packages))}")

    def upgrade(self, *packages: str, env: str = "") -> None:
        """Bump conda + pypi constraints to the latest allowed, then sync in."""
        self.sync()
        self.pixi("upgrade", *packages, feature=env)
        self.pull()
        self.console.print(
            f"[green]upgraded[/green] {escape(', '.join(packages) or 'all conda + pypi deps')}"
        )

    def remove(self, *packages: str) -> None:
        """Remove packages from the manifest wherever declared, then re-sync."""
        document = Document(self.manifest)
        removed = document.remove(packages)
        document.save()
        gone = ", ".join(dict.fromkeys(removed)) or "(nothing found)"
        self.console.print(f"[green]removed[/green] {escape(gone)}")
        self.sync()

    def pull(self) -> None:
        """Mirror pixi's resolved deps back into the manifest."""
        document = Document(self.manifest)
        document.pull(tomlkit.parse(self.pixi.manifest.read_text()).unwrap())
        document.save()

    @staticmethod
    def row_status(spec: str, version: str | None) -> tuple[str, str, str]:
        """The (mark, shown version, tally bucket) for a declared dep vs what's installed."""
        if version is None:
            return "[red]✗ missing[/red]", "[dim]·[/dim]", "missing"
        if satisfied(spec, version):
            return "[green]✓[/green]", version, "ok"
        return "[yellow]≠ drift[/yellow]", f"[yellow]{version}[/yellow]", "drift"

    def tree(self, env: str = "default") -> None:
        """Show declared vs installed deps, each checked in its own ecosystem."""
        declared = self.declared(env)
        provisioned = self.pixi.installed(env)
        by_source: dict[str, dict[str, str]] = {
            "npm": {n: inst.version for n, inst in self.node(self.load()).installed(env).items()},
            "cargo": {name: inst.version for name, inst in self.cargo.installed(env).items()},
        }
        for name, inst in provisioned.items():
            by_source.setdefault(inst.kind, {})[name] = inst.version
        table = Table(title=f"{NAME} · {env} · declared vs installed", header_style="bold cyan")
        for column in ("package", "source", "declared", "installed", ""):
            table.add_column(column)
        tally: Counter[str] = Counter()
        for name, dep in sorted(declared.items()):
            installed = by_source.get(dep.source, {}).get(name)
            mark, shown, bucket = self.row_status(dep.spec, installed)
            tally[bucket] += 1
            table.add_row(name, dep.source, dep.spec, shown, mark)
        self.console.print(table)
        transitive = sum(1 for inst in provisioned.values() if not inst.explicit)
        self.console.print(
            f"[green]{tally['ok']} ok[/green] · [yellow]{tally['drift']} drift[/yellow] · "
            f"[red]{tally['missing']} missing[/red] · [dim]{transitive} transitive installed[/dim]"
        )
