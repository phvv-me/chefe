import os
from collections.abc import Generator
from contextlib import contextmanager

from packaging.utils import canonicalize_name
from plumbum import local
from rich.console import Console

from ..backends import Cargo, Node, Pixi
from ..core import current_platform
from ..manifest import Manifest, Spec
from ..report import markup
from .compiler import Compiler
from .generated import GeneratedFiles
from .layout import Workspace


class Runtime:
    """The provisioned environment as the rest of chefe sees it: PATH, toolchains, versions.

    Entering it recompiles first when the manifest has moved on, so no command is ever served
    env vars or binaries from a `.chefe/` that no longer matches `chefe.toml`.
    """

    def __init__(
        self,
        workspace: Workspace,
        compiler: Compiler,
        pixi: Pixi,
        cargo: Cargo,
        console: Console,
    ) -> None:
        self.workspace = workspace
        self.compiler = compiler
        self.pixi = pixi
        self.cargo = cargo
        self.console = console

    @contextmanager
    def activated(self, env: str = "default") -> Generator[None]:
        """Expose managed ecosystem executables on PATH for commands and shells.

        Recompiles first when the manifest changed since the last sync, so an edit to
        `chefe.toml` (a new env var, a dep) is never served from a stale generated env.
        """
        # Check and recompile inside ONE lock acquisition: the unlocked
        # check-then-act here was how two processes both recompiled and one
        # read the other's half-finished truth (the 2026-08-14 race).
        with GeneratedFiles(directory=self.workspace.out).locked() as files:
            if self.compiler.stale(env):
                name = self.workspace.manifest.name
                self.console.print(markup(t"[yellow]{name} changed, recompiling[/yellow]"))
                self.compiler.write(files, env)
                self.compiler.announce()
        with self.pixi.activated(env):
            manifest = self.workspace.load()
            toolchains = manifest.toolchains_for(env, platform=current_platform())
            binary_dirs = [
                self.node(env, manifest).binary_dir(),
                *[
                    self.workspace.out / path
                    for spec in toolchains.values()
                    for path in spec.bin_dirs
                ],
            ]
            path = local.env["PATH"]
            prefix = os.pathsep.join(str(path) for path in binary_dirs if path.is_dir())
            with local.env(PATH=f"{prefix}{os.pathsep}{path}" if prefix else path):
                yield

    def installed_by_source(self, env: str) -> dict[str, dict[str, str]]:
        """Installed versions for ``env`` grouped by manifest source (conda/python/nodejs/rust).

        Each ecosystem is queried through its own backend, and pixi's `pypi` kind is folded onto
        the `python` source so a declared dep lines up with what got provisioned for it.
        """
        node = self.node(env)
        by_source: dict[str, dict[str, str]] = {
            "nodejs": {n: i.shown_version for n, i in node.installed(env).items()},
            "rust": {n: i.shown_version for n, i in self.cargo.installed(env).items()},
        }
        for name, inst in self.pixi.installed(env).items():
            source = inst.source
            installed_name = canonicalize_name(name) if source == "python" else name
            by_source.setdefault(source, {})[installed_name] = inst.shown_version
            if inst.kind == "conda":
                by_source.setdefault("python", {}).setdefault(
                    canonicalize_name(name), inst.shown_version
                )
        return by_source

    def node(self, env: str, manifest: Manifest | None = None) -> Node:
        """The Node.js backend for ``env``, aimed at this workspace's install directory."""
        return Node.for_env(
            manifest if manifest is not None else self.workspace.load(),
            env,
            root=self.workspace.root,
            out=self.workspace.out,
        )

    def provision(self, env: str, *, resolve: bool) -> None:
        """Make ``env`` match the manifest across every language and toolchain.

        The whole provisioning runs under the workspace lock, not just the compile. Several
        agents share one checkout here, and holding the lock only across the compile let one
        process rewrite the manifest while another was still solving against it, which is how a
        workspace ends up with a manifest and a lock that disagree.
        """
        with GeneratedFiles(directory=self.workspace.out).locked() as files:
            self.compiler.write(files, env)
            self.compiler.announce()
            self.compiler.install_locked(files, env, resolve=resolve)
            with self.activated(env):
                self.node(env)("install")
            self.cargo.sync(env, self.rust_deps(env))

    def provision_language(self, language: str, *, env: str) -> None:
        """Install a freshly added `language` dep into ``env``, so `chefe run` finds it at once.

        `pixi add` installs what it adds, and this is the counterpart for the toolchains chefe
        drives itself: without it, an added nodejs/rust dep sat in the manifest until the next
        full `chefe install` and `chefe run <bin>` failed with command-not-found.

        The set is closed at nodejs and rust on purpose, because those are the only two
        ecosystems chefe installs with a backend of its own. Every other toolchain is pixi's, so
        it is already provisioned by the time this runs, and a language named here that chefe
        does not drive would be a promise no backend keeps.
        """
        if language == "nodejs":
            with self.activated(env):
                self.node(env)("install")
        if language == "rust":
            self.cargo.sync(env, self.rust_deps(env))

    def rust_deps(self, env: str) -> dict[str, Spec]:
        """Cargo-installable crate specs declared by `[rust]` for ``env``."""
        manifest = self.workspace.load()
        rust = manifest.toolchains_for(env, platform=current_platform()).get("rust")
        return rust.all_deps() if rust else {}

    def update_all(self, env: str) -> None:
        """Refresh Pixi, Node, and Cargo packages within one environment's constraints."""
        self.compiler.sync(env)
        self.pixi("update", "-e", env)
        with self.activated(env):
            self.node(env)("update")
        self.cargo.update(env, self.rust_deps(env))
