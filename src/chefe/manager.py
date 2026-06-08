import os
import shutil
import tomllib
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated

import tomlkit
from cyclopts import Parameter
from plumbum import local
from pydantic import ValidationError
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from . import ENV_DIR, MANIFEST, NAME, PIXI_RESOLVED
from .backends import Cargo, Node, Pixi
from .compiled import PackageJson, PixiManifest
from .errors import ChefeError, ManifestValidationMessage
from .manifest import Document, Manifest, Spec
from .state import Declared
from .utils import current_platform, satisfied


class PackageManager:
    """A workspace: one manifest, compiled into a generated env and run by the real tools."""

    def __init__(self, root: Path = Path()) -> None:
        # Absolute so the env bin dirs put on PATH stay valid when a backend runs
        # from inside the env: a relative npm path breaks once the cwd changes.
        root = root.absolute()
        self.manifest = root / MANIFEST
        self.root = root
        self.out = root / ENV_DIR
        self.pixi = Pixi(self.out)
        self.cargo = Cargo(self.out, self.pixi)
        self.console = Console()

    def load(self) -> Manifest:
        """The validated manifest."""
        if not self.manifest.exists():
            raise ChefeError(
                f"{self.manifest.name} not found. "
                "Run `chefe init` first, or run chefe from a workspace root."
            )
        try:
            return Manifest.load(self.manifest)
        except tomllib.TOMLDecodeError as error:
            raise ChefeError(f"{self.manifest.name} has invalid TOML: {error}") from error
        except ValidationError as error:
            raise ChefeError(ManifestValidationMessage(self.manifest, error).text()) from error

    def node(self, manifest: Manifest) -> Node:
        """The Node.js backend for this manifest: manager binary plus install dir."""
        nodejs = manifest.toolchains().get("nodejs")
        app = nodejs.app if nodejs is not None else False
        manager = nodejs.manager if nodejs is not None and nodejs.manager else "npm"
        directory = self.root if app else self.out
        return Node(directory, manager)

    def declared(self, env: str) -> dict[str, Declared]:
        """Every dep declared for ``env`` on this host."""
        return self.load().declared(env, current_platform())

    @contextmanager
    def activated(self, env: str = "default") -> Iterator[None]:
        """Expose managed ecosystem executables on PATH for commands and shells."""
        with self.pixi.activated(env):
            manifest = self.load()
            toolchains = manifest.toolchains_for(env, current_platform())
            binary_dirs = [
                self.node(manifest).binary_dir(),
                *[self.out / path for spec in toolchains.values() for path in spec.bin_dirs],
            ]
            path = local.env["PATH"]
            prefix = os.pathsep.join(str(path) for path in binary_dirs if path.is_dir())
            with local.env(PATH=f"{prefix}{os.pathsep}{path}" if prefix else path):
                yield

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
        """Sync, then make ``env`` match the manifest across every language/toolchain."""
        self.sync()
        self.pixi("install", "-e", env)
        with self.activated(env):
            self.node(self.load())("install")
        crates = self.rust_deps(env)
        self.cargo.sync(env, crates)
        self.console.print(f"[green]installed[/green] env [bold]{escape(env)}[/bold]")

    def update(self, env: str = "default") -> None:
        """Re-solve to the newest allowed versions across ecosystems."""
        self.sync()
        self.pixi("update", "-e", env)
        with self.activated(env):
            self.node(self.load())("update")
        self.console.print(f"[green]updated[/green] env [bold]{escape(env)}[/bold]")

    def rust_deps(self, env: str) -> dict[str, str]:
        """Cargo-installable crates declared by `[rust]`."""
        manifest = self.load()
        rust = manifest.toolchains_for(env, current_platform()).get("rust")
        return {
            name: spec.version or "*" for name, spec in (rust.all_deps() if rust else {}).items()
        }

    def clean(self) -> None:
        """Remove the generated env and manifests."""
        shutil.rmtree(self.out, ignore_errors=True)
        self.console.print(f"[green]removed[/green] {self.out.name}/")

    def global_install(self, name: str = "") -> None:
        """Install every language/toolchain's declared deps into one shared global pixi env.

        Conda goes through `pixi global`; adapters then use binaries from that global env for
        languages that need a second install step, such as Python, Node.js, and Rust.
        """
        manifest = self.load()
        name = name or manifest.workspace.name

        def spec(pkg: str, dep: Spec) -> str:
            return pkg if dep.version in (None, "*") else f"{pkg}{dep.version}"

        toolchains = manifest.toolchains()
        conda = dict(manifest.deps)
        self.pixi.global_install(name, [spec(pkg, dep) for pkg, dep in conda.items()])

        prefix = self.pixi.global_prefix(name)
        if (python := toolchains.get("python")) and python.all_deps():
            self.pixi.global_pip(prefix, [spec(p, d) for p, d in python.all_deps().items()])
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
            f"[green]installed[/green] {total} deps into [bold]{escape(name)}[/bold]"
        )

    def run(self, task: str, *args: Annotated[str, Parameter(allow_leading_hyphen=True)]) -> None:
        """Run a task or installed executable inside the env, exiting with its code."""
        with self.activated():
            code = self.pixi.exit_code("run", task, *args)
        if code:
            raise SystemExit(code)

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
        with self.activated(env):
            self.pixi("shell", "-e", env)

    def add(
        self,
        *packages: str,
        language: Annotated[
            str,
            Parameter(
                name=("--language", "-l"),
                help="conda, python, or any runtime/toolchain declared in [deps].",
            ),
        ] = "conda",
        env: str = "",
        spec: str = "*",
    ) -> None:
        """Add packages to the manifest, then sync; conda + Python resolve through pixi.

        `language`: `conda`, `python`, or any runtime declared in `[deps]`.
        """
        if not packages:
            raise ChefeError("No packages given. Usage: `chefe add <package> [-l language]`.")
        manifest = self.load()
        source = self.source_for_language(language)
        self.require_language(manifest, language, source, env)
        if source in PIXI_RESOLVED:
            self.sync()
            self.pixi(
                "add", *self.package_specs(packages, spec), pypi=source == "python", feature=env
            )
            self.pull()
        else:
            document = Document(self.manifest)
            document.add(source, env, packages, spec)
            document.save()
            self.sync()
        self.console.print(f"[green]added[/green] {escape(', '.join(packages))}")

    @staticmethod
    def package_specs(packages: tuple[str, ...], spec: str) -> tuple[str, ...]:
        """Package args with a shared version spec, in the form Pixi expects."""
        return packages if spec in ("", "*") else tuple(f"{package}{spec}" for package in packages)

    @staticmethod
    def source_for_language(language: str) -> str:
        """Map user-facing language names to internal dependency source tables."""
        if not language:
            raise ChefeError("Language cannot be empty. Omit it for conda, or use `-l python`.")
        return language

    def require_language(self, manifest: Manifest, language: str, source: str, env: str) -> None:
        """Validate that a non-Pixi language is declared before writing its package table."""
        if source == "conda":
            return
        scope = manifest if not env else manifest.envs.get(env)
        table = "[deps]" if not env else f"[envs.{env}.deps]"
        if scope is None:
            raise ChefeError(
                f"Environment `{env}` does not exist. "
                f'Declare `{source} = "*"` under {table} before using `-l {language}`.'
            )
        if source not in scope.deps:
            raise ChefeError(
                f"Language `{language}` is not declared in {table}. "
                f'Add `{source} = "*"` there before using `-l {language}`.'
            )

    def upgrade(self, *packages: str, env: str = "") -> None:
        """Bump conda + Python constraints to the latest allowed, then sync in."""
        self.sync()
        self.pixi("upgrade", *packages, feature=env)
        self.pull()
        self.console.print(
            f"[green]upgraded[/green] {escape(', '.join(packages) or 'all conda + Python deps')}"
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
        node_installed = {
            n: inst.version for n, inst in self.node(self.load()).installed(env).items()
        }
        cargo_installed = {name: inst.version for name, inst in self.cargo.installed(env).items()}
        by_source: dict[str, dict[str, str]] = {
            "nodejs": node_installed,
            "rust": cargo_installed,
        }
        for name, inst in provisioned.items():
            by_source.setdefault(inst.kind, {})[name] = inst.version
        table = Table(title=f"{NAME} · {env} · declared vs installed", header_style="bold cyan")
        for column in ("package", "language", "declared", "installed", ""):
            table.add_column(column)
        tally: Counter[str] = Counter()
        for name, dep in sorted(declared.items()):
            installed = by_source.get(dep.source, {}).get(name)
            mark, shown, bucket = self.row_status(dep.spec, installed)
            tally[bucket] += 1
            table.add_row(name, self.language_for_source(dep.source), dep.spec, shown, mark)
        self.console.print(table)
        transitive = sum(1 for inst in provisioned.values() if not inst.explicit)
        self.console.print(
            f"[green]{tally['ok']} ok[/green] · [yellow]{tally['drift']} drift[/yellow] · "
            f"[red]{tally['missing']} missing[/red] · [dim]{transitive} transitive installed[/dim]"
        )

    @staticmethod
    def language_for_source(source: str) -> str:
        """Map internal dependency source tables to user-facing language names."""
        return source
