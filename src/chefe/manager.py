from functools import cache, cached_property
from pathlib import Path

from rich.console import Console

from .backends import Cargo, Pixi, PixiGlobal
from .core import Model
from .shared import GlobalEnv
from .workspace import (
    DependencyCommands,
    EnvironmentCommands,
    ExecutionCommands,
    Workspace,
)
from .workspace.compiler import Compiler
from .workspace.runtime import Runtime


@cache
def _reports() -> Console:
    """The one console every command group reports progress through, shared process-wide."""
    return Console()


@cache
def _failures() -> Console:
    """The one console failures are reported through.

    Failures are diagnostics, so they go to stderr and a caller redirecting stdout
    (`chefe install > log`) still sees them.
    """
    return Console(stderr=True)


class PackageManager(Model):
    """A workspace: one manifest, compiled into a generated env and run by the real tools.

    Nothing is done here. This wires the collaborators and exposes them as the four command
    groups the CLI registers, so the command surface a user sees and the objects that implement
    it line up one to one. A workspace root is all a caller gives; every collaborator below is
    built once on first use and kept, so each of them sees the same manifest and backend however
    it was reached.
    """

    root: Path | None = None

    @cached_property
    def compiler(self) -> Compiler:
        """Turns the declared manifest into the generated one the backend runs."""
        return Compiler(self.workspace, self.pixi, _reports())

    @cached_property
    def dependencies(self) -> DependencyCommands:
        """`chefe tree|add|upgrade|remove`."""
        return DependencyCommands(
            self.workspace, self.compiler, self.runtime, self.pixi, _reports()
        )

    @cached_property
    def environment(self) -> EnvironmentCommands:
        """`chefe init|sync|install|activate|update|clean`."""
        return EnvironmentCommands(
            self.workspace, self.compiler, self.runtime, self.pixi, _reports()
        )

    @property
    def errors(self) -> Console:
        """The channel failures are reported on."""
        return _failures()

    @cached_property
    def execution(self) -> ExecutionCommands:
        """`chefe run|x|shell`."""
        return ExecutionCommands(self.workspace, self.runtime, self.pixi)

    @cached_property
    def glob(self) -> GlobalEnv:
        """`chefe global ...`, which acts on the shared env rather than this workspace."""
        return GlobalEnv(PixiGlobal(), self.workspace.load, _reports())

    @cached_property
    def pixi(self) -> Pixi:
        """The backend pinned to the manifest compiled into the workspace's generated env dir."""
        return Pixi(self.workspace.out)

    @cached_property
    def runtime(self) -> Runtime:
        """Provisions a compiled env and keeps every ecosystem in it up to date."""
        return Runtime(self.workspace, self.compiler, self.pixi, Cargo(self.pixi), _reports())

    @cached_property
    def workspace(self) -> Workspace:
        """Where the manifest is and what it says."""
        return Workspace(self.root)
