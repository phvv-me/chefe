from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

import tomlkit
from pydantic import ValidationError
from tomlkit import TOMLDocument
from tomlkit.items import AbstractTable, InlineTable, Table

from ...core import ChefeError, Toml, manifest_validation_text
from ..schema import Manifest
from .lookup import declared_key, dep_path, dep_tables, dig, normalize, pixi_scopes, version_of

# Keys that mark a runtime-keyed toolchain table (mirrors `ToolchainSpec`'s fields), so
# `remove` can tell `[nodejs]` apart from structural tables like `[workspace]`.
_TOOLCHAIN_MARKERS = ("deps", "dev", "manager", "app", "package", "bin_dirs", "indexes")

# Manifest tables that are structure, never runtime-keyed toolchains, so removing a package
# that happens to share their name (`chefe remove dev`) must not delete them.
_STRUCTURAL_TABLES = {
    "workspace",
    "deps",
    "dev",
    "envs",
    "on",
    "env",
    "tasks",
    "activation",
    "modules",
    "system",
}

# Namespace tables whose direct children are scopes (an env, a platform overlay), never
# toolchain tables, so a removed package sharing an env or platform name leaves them intact.
_SCOPE_NAMESPACES = ("envs", "on")


class Document:
    """Editable tomlkit view of the manifest (comments kept); the write twin of `Manifest`.

    Every method here changes the parsed document or persists it. Where a write needs to know
    which table already declares a package, it asks the read-only lookups beside it.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.doc: TOMLDocument = tomlkit.parse(path.read_text())

    @classmethod
    def bump(cls, table: Table, key: str, spec: Toml) -> None:
        """Update the declared ``key`` to ``spec``'s resolved version, keeping its shape.

        A spec without a version (git / path / url sources) has nothing to bump, so the
        declaration stays exactly as written.
        """
        version = version_of(spec)
        if version is None:
            return
        if isinstance(table[key], str):
            table[key] = version
        else:
            cast(InlineTable, table[key])["version"] = version

    def add(self, source: str, *, env: str, packages: Sequence[str], spec: str) -> None:
        """Write ``packages`` at ``spec`` into the ``source`` dep table."""
        table = self.table(dep_path(source, env=env))
        for package in packages:
            table[package] = spec

    def fold(self, resolved: Mapping[str, Toml], paths: Sequence[list[str]]) -> None:
        """Bump each resolved dep in the first candidate table declaring it; add new deps.

        Additions land at ``paths[0]`` (the most specific scope), and tables are only created
        when something is actually added, so a family-scoped declaration is bumped in place
        instead of duplicated under a concrete platform.
        """
        for name, spec in resolved.items():
            if not self._bump_declared(name, spec, paths):
                self.table(paths[0])[name] = spec

    def merge(self, table: Table, resolved: Mapping[str, Toml]) -> None:
        """Bump versions of deps already in ``table`` (keeping index/source); add what's new."""
        for name, spec in resolved.items():
            if (key := declared_key(table, name)) is not None:
                self.bump(table, key, spec)
            else:
                table[name] = spec

    def pull(self, pixi_doc: Mapping[str, Toml]) -> None:
        """Fold pixi's resolved conda + Python deps from a `pixi.toml` dict back into the manifest.

        Walks the base scope, each feature, and each target (including targets nested inside
        features), bumping declared versions where they are written and adding what pixi added,
        while keeping comments and index aliases intact. A target's deps may be declared under
        any covering selector (`[on.linux]` covers `target.linux-64`), so each pixi scope maps
        to the ordered candidate paths that can declare it.
        """
        for at, dests in pixi_scopes(pixi_doc):
            for source, sub in (
                ("dependencies", ["deps"]),
                ("pypi-dependencies", ["python", "deps"]),
            ):
                resolved = dig(pixi_doc, *at, source)
                if resolved:
                    self.fold(resolved, [[*dest, *sub] for dest in dests])

    def remove(self, packages: Sequence[str]) -> list[str]:
        """Drop ``packages`` from every dep table; return the names actually removed."""
        tables = dep_tables(self.doc)
        removed = [p for t in tables for p in packages if t.pop(p, None) is not None]
        self.remove_source_tables(self.doc, packages)
        return removed

    def remove_source_tables(
        self,
        node: AbstractTable | TOMLDocument,
        packages: Sequence[str],
        *,
        scoped: bool = True,
    ) -> None:
        """Remove runtime-keyed source tables when their runtime package is removed.

        A toolchain table only ever sits directly inside a scope (the root, `[dev]`, an env,
        a platform overlay). Structural tables and the children of the `envs`/`on` namespaces
        (envs and platforms themselves) merely share the shape, so a removed package that
        happens to carry their name (`chefe remove serving` against `[envs.serving]`) must
        recurse past them, never delete them.
        """
        targets = {normalize(package) for package in packages}
        for key, value in list(node.items()):
            if not isinstance(value, AbstractTable):
                continue
            toolchain = scoped and normalize(key) not in _STRUCTURAL_TABLES
            if (
                toolchain
                and normalize(key) in targets
                and any(m in value for m in _TOOLCHAIN_MARKERS)
            ):
                node.pop(key, None)
            else:
                self.remove_source_tables(value, packages, scoped=key not in _SCOPE_NAMESPACES)

    def save(self) -> None:
        """Write the document back to disk, refusing to persist a manifest `load` would reject.

        Every writer funnels through here, so no chefe command can wedge the workspace by
        saving a manifest that the next command fails to parse or validate.
        """
        text = tomlkit.dumps(self.doc)
        try:
            Manifest.from_toml(text)
        except ValidationError as error:
            raise ChefeError(manifest_validation_text(self.path, error)) from error
        self.path.write_text(text)

    def table(self, path: Sequence[str]) -> Table:
        """The table at ``path``, creating intermediate tables as needed."""
        node: Table | TOMLDocument = self.doc
        for key in path:
            if key not in node:
                node[key] = tomlkit.table()
            node = cast(Table, node[key])
        return cast(Table, node)

    def _bump_declared(self, name: str, spec: Toml, paths: Sequence[list[str]]) -> bool:
        """Bump ``name`` in the first of ``paths`` declaring it, reporting whether one did.

        Nothing is created here, so a scope that does not declare the dep is left exactly as it
        was and the caller decides where an addition belongs.
        """
        for path in paths:
            table = dig(self.doc, *path)
            if (key := declared_key(table, name)) is not None:
                self.bump(cast(Table, table), key, spec)
                return True
        return False
