from collections.abc import Sequence
from typing import Annotated

import tomlkit
from cyclopts import Parameter
from rich.console import Console

from ...backends import Pixi
from ...core import ChefeError, Project
from ...manifest import Document, Manifest, Runtimes
from ...report import TreeReport, markup
from ..compiler import Compiler
from ..layout import Workspace
from ..runtime import Runtime


class DependencyCommands:
    """`chefe tree|add|upgrade|remove`: reading and editing what the manifest declares.

    A dep pixi resolves itself (conda, Python) is added through pixi and mirrored back, while
    every other toolchain is written into the manifest here and provisioned by its own backend,
    so an added dep is runnable the moment the command returns either way.
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

    @staticmethod
    def package_specs(packages: Sequence[str], spec: str) -> Sequence[str]:
        """Package args with a shared version spec, in the form Pixi expects."""
        return packages if spec in ("", "*") else [f"{package}{spec}" for package in packages]

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
        """Add packages to the manifest, then sync and provision so they run right away.

        `language`: `conda`, `python`, or any runtime declared in `[deps]`.
        """
        if not packages:
            raise ChefeError("No packages given. Usage: `chefe add <package> [-l language]`.")
        self.workspace.editable_manifest()
        source = Runtimes.source(language)
        self.require_language(self.workspace.load(), source, env=env)
        if source in Project.pixi_resolved:
            self.add_through_pixi(packages, source=source, env=env, spec=spec)
        else:
            self.add_to_manifest(packages, source=source, env=env, spec=spec)
        self.console.print(markup(t"[green]added[/green] {', '.join(packages)}"))

    def add_through_pixi(
        self, packages: Sequence[str], *, source: str, env: str, spec: str
    ) -> None:
        """Let pixi add and solve the packages, then mirror its answer back into the manifest.

        Pixi owns conda and Python resolution, so it edits the generated manifest and the answer
        it lands on is read back rather than guessed.
        """
        self.compiler.sync()
        self.pixi("add", *self.package_specs(packages, spec), pypi=source == "python", feature=env)
        self.pull()

    def add_to_manifest(
        self, packages: Sequence[str], *, source: str, env: str, spec: str
    ) -> None:
        """Write the packages into `chefe.toml` and provision them with their own backend.

        Every toolchain pixi does not resolve is declared by chefe itself, so the manifest is the
        source of truth here and the compile that follows is what its backend installs from.
        """
        document = Document(self.workspace.manifest)
        document.add(source, env=env, packages=packages, spec=spec)
        document.save()
        target = env or "default"
        self.compiler.sync(target)
        self.runtime.provision_language(source, env=target)

    def pull(self) -> None:
        """Mirror pixi's resolved deps back into the manifest."""
        document = Document(self.workspace.manifest)
        document.pull(tomlkit.parse(self.pixi.manifest.read_text()).unwrap())
        document.save()

    def remove(self, *packages: str) -> None:
        """Remove packages from the manifest wherever declared, then re-sync."""
        self.workspace.editable_manifest()
        document = Document(self.workspace.manifest)
        removed = document.remove(packages)
        document.save()
        gone = ", ".join(dict.fromkeys(removed)) or "(nothing found)"
        self.console.print(markup(t"[green]removed[/green] {gone}"))
        self.compiler.sync()

    def require_language(self, manifest: Manifest, language: str, *, env: str) -> None:
        """Validate that a non-Pixi language is declared before writing its package table.

        The language name doubles as the manifest's dependency source table, so an env-scoped
        language may be declared either in the env or at the root `[deps]`.
        """
        if language == "conda":
            return
        scope = manifest if not env else manifest.envs.get(env)
        if scope is None:
            raise ChefeError(self._missing_env_message(language, env=env))
        declared = set(scope.deps) | set(manifest.deps)
        if Runtimes.providers(language).isdisjoint(declared):
            raise ChefeError(self._undeclared_language_message(language, env=env))

    def tree(
        self, env: str = "default", plan: Annotated[bool, Parameter(name="--plan")] = False
    ) -> None:
        """Show declared vs installed deps, each checked in its own ecosystem.

        `--plan` turns the report into a dry run: instead of the full table, it lists what a
        `chefe install` would change (install the missing, update the drifted, remove the
        explicit deps no longer declared) without touching the env.
        """
        declared = self.workspace.declared(env)
        by_source = self.runtime.installed_by_source(env)
        provisioned = self.pixi.installed(env)
        report = TreeReport(self.console)
        if plan:
            report.plan(env, declared, by_source, provisioned)
        else:
            report.table(env, declared, by_source, provisioned)

    def upgrade(self, *packages: str, env: str = "") -> None:
        """Update safely within constraints, or loosen constraints for named packages."""
        self.workspace.editable_manifest()
        target = env or "default"
        if not packages:
            self.upgrade_all(target)
            return
        self.compiler.sync(target)
        self.pixi("upgrade", *packages, feature=env)
        self.pull()
        self.console.print(markup(t"[green]upgraded[/green] {', '.join(packages)}"))

    def upgrade_all(self, env: str) -> None:
        """Refresh every ecosystem in ``env`` without loosening a single declared constraint."""
        self.runtime.update_all(env)
        self.console.print(
            markup(
                t"[green]upgraded[/green] every ecosystem in env "
                t"[bold]{env}[/bold] within constraints"
            )
        )

    @staticmethod
    def _deps_table(env: str) -> str:
        """The manifest table a language would be declared under for `env`."""
        return "[deps]" if not env else f"[envs.{env}.deps]"

    def _missing_env_message(self, language: str, *, env: str) -> str:
        """Error text for `-l <language>` naming an environment that does not exist."""
        table = self._deps_table(env)
        return (
            f"Environment `{env}` does not exist. "
            f'Declare `{language} = "*"` under {table} before using `-l {language}`.'
        )

    def _undeclared_language_message(self, language: str, *, env: str) -> str:
        """Error text for `-l <language>` whose provider is missing from its scope."""
        table = self._deps_table(env)
        return (
            f"Language `{language}` is not declared in {table}. "
            f'Add `{language} = "*"` there before using `-l {language}`.'
        )
