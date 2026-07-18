from collections.abc import Mapping
from pathlib import Path
from typing import cast

import tomlkit
from pydantic import ValidationError
from tomlkit import TOMLDocument
from tomlkit.items import AbstractTable, InlineTable, Table

from ..base import Toml
from ..errors import ChefeError, manifest_validation_text
from ..utils import platform_scopes
from .schema import Manifest

# Keys that mark a runtime-keyed toolchain table (mirrors `ToolchainSpec`'s fields), so
# `remove` can tell `[nodejs]` apart from structural tables like `[workspace]`.
TOOLCHAIN_MARKERS = ("deps", "dev", "manager", "app", "package", "bin_dirs", "indexes")

# Manifest tables that are structure, never runtime-keyed toolchains, so removing a package
# that happens to share their name (`chefe remove dev`) must not delete them.
STRUCTURAL_TABLES = frozenset(
    {"workspace", "deps", "dev", "envs", "on", "env", "tasks", "activation", "modules", "system"}
)

# Namespace tables whose direct children are scopes (an env, a platform overlay), never
# toolchain tables, so a removed package sharing an env or platform name leaves them intact.
SCOPE_NAMESPACES = ("envs", "on")


class Document:
    """Editable tomlkit view of the manifest (comments kept); the write twin of `Manifest`."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.doc: TOMLDocument = tomlkit.parse(path.read_text())

    @staticmethod
    def dep_path(source: str, env: str) -> list[str]:
        """The deps table path for ``source`` (conda = bare `[deps]`), nested under ``env``."""
        base = ["deps"] if source == "conda" else [source, "deps"]
        return ["envs", env, *base] if env else base

    @staticmethod
    def normalize(name: str) -> str:
        """Canonical package key for matching (case- and `_`/`-`-insensitive)."""
        return name.lower().replace("_", "-")

    @staticmethod
    def dig(data: Mapping[str, Toml], *keys: str) -> Mapping[str, Toml]:
        """Walk ``keys`` into a nested table, returning the leaf mapping (or empty)."""
        node: Toml | Mapping[str, Toml] = data
        for key in keys:
            node = node.get(key, {}) if isinstance(node, Mapping) else {}
        return node if isinstance(node, Mapping) else {}

    @classmethod
    def dep_tables(cls, node: Mapping[str, Toml]) -> list[AbstractTable]:
        """Every nested `deps` table in ``node``, whether a section or an inline table."""
        tables: list[AbstractTable] = []
        for key, value in node.items():
            if key == "deps" and isinstance(value, AbstractTable):
                tables.append(value)
            elif isinstance(value, Mapping):
                tables.extend(cls.dep_tables(value))
        return tables

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

    def table(self, path: list[str]) -> Table:
        """The table at ``path``, creating intermediate tables as needed."""
        node: Table | TOMLDocument = self.doc
        for key in path:
            if key not in node:
                node[key] = tomlkit.table()
            node = cast(Table, node[key])
        return cast(Table, node)

    def add(self, source: str, env: str, packages: tuple[str, ...], spec: str) -> None:
        """Write ``packages`` at ``spec`` into the ``source`` dep table."""
        table = self.table(self.dep_path(source, env))
        for package in packages:
            table[package] = spec

    def remove(self, packages: tuple[str, ...]) -> list[str]:
        """Drop ``packages`` from every dep table; return the names actually removed."""
        tables = self.dep_tables(self.doc)
        removed = [p for t in tables for p in packages if t.pop(p, None) is not None]
        self.remove_source_tables(self.doc, packages)
        return removed

    def remove_source_tables(
        self, node: AbstractTable | TOMLDocument, packages: tuple[str, ...], scoped: bool = True
    ) -> None:
        """Remove runtime-keyed source tables when their runtime package is removed.

        A toolchain table only ever sits directly inside a scope (the root, `[dev]`, an env,
        a platform overlay). Structural tables and the children of the `envs`/`on` namespaces
        (envs and platforms themselves) merely share the shape, so a removed package that
        happens to carry their name (`chefe remove serving` against `[envs.serving]`) must
        recurse past them, never delete them.
        """
        targets = {self.normalize(package) for package in packages}
        for key, value in tuple(node.items()):
            if not isinstance(value, AbstractTable):
                continue
            toolchain = scoped and self.normalize(key) not in STRUCTURAL_TABLES
            if (
                toolchain
                and self.normalize(key) in targets
                and any(m in value for m in TOOLCHAIN_MARKERS)
            ):
                node.pop(key, None)
            else:
                self.remove_source_tables(value, packages, scoped=key not in SCOPE_NAMESPACES)

    def pull(self, pixi_doc: Mapping[str, Toml]) -> None:
        """Fold pixi's resolved conda + Python deps from a `pixi.toml` dict back into the manifest.

        Walks the base scope, each feature, and each target (including targets nested inside
        features), bumping declared versions where they are written and adding what pixi added,
        while keeping comments and index aliases intact. A target's deps may be declared under
        any covering selector (`[on.linux]` covers `target.linux-64`), so each pixi scope maps
        to the ordered candidate paths that can declare it.
        """
        for at, dests in self.scopes(pixi_doc):
            for source, sub in (
                ("dependencies", ["deps"]),
                ("pypi-dependencies", ["python", "deps"]),
            ):
                resolved = self.dig(pixi_doc, *at, source)
                if resolved:
                    self.fold(resolved, [[*dest, *sub] for dest in dests])

    def scopes(
        self, pixi_doc: Mapping[str, Toml]
    ) -> list[tuple[tuple[str, ...], list[list[str]]]]:
        """Each pixi scope paired with the manifest paths that can declare its deps.

        The `dev` feature is compiled from the manifest's `[dev]` table, so it folds back
        there rather than into a fabricated `[envs.dev]`.
        """
        scopes: list[tuple[tuple[str, ...], list[list[str]]]] = [((), [[]])]
        for name in self.dig(pixi_doc, "feature"):
            dest = ["dev"] if name == "dev" else ["envs", name]
            scopes.append(((("feature", name)), [dest]))
            for plat in self.dig(pixi_doc, "feature", name, "target"):
                scopes.append(
                    (
                        ("feature", name, "target", plat),
                        [[*dest, "on", key] for key in platform_scopes(plat)],
                    )
                )
        for plat in self.dig(pixi_doc, "target"):
            scopes.append((("target", plat), [["on", key] for key in platform_scopes(plat)]))
        return scopes

    def fold(self, resolved: Mapping[str, Toml], paths: list[list[str]]) -> None:
        """Bump each resolved dep in the first candidate table declaring it; add new deps.

        Additions land at ``paths[0]`` (the most specific scope), and tables are only created
        when something is actually added, so a family-scoped declaration is bumped in place
        instead of duplicated under a concrete platform.
        """
        for name, spec in resolved.items():
            for path in paths:
                table = self.dig(self.doc, *path)
                if (key := self.declared_key(table, name)) is not None:
                    self.bump(cast(Table, table), key, spec)
                    break
            else:
                self.table(paths[0])[name] = spec

    def merge(self, table: Table, resolved: Mapping[str, Toml]) -> None:
        """Bump versions of deps already in ``table`` (keeping index/source); add what's new."""
        for name, spec in resolved.items():
            if (key := self.declared_key(table, name)) is not None:
                self.bump(table, key, spec)
            else:
                table[name] = spec

    @classmethod
    def declared_key(cls, table: Mapping[str, Toml], name: str) -> str | None:
        """The key in ``table`` declaring ``name``, matched through `normalize` (or `None`)."""
        target = cls.normalize(name)
        return next((key for key in table if cls.normalize(key) == target), None)

    @classmethod
    def bump(cls, table: Table, key: str, spec: Toml) -> None:
        """Update the declared ``key`` to ``spec``'s resolved version, keeping its shape.

        A spec without a version (git / path / url sources) has nothing to bump, so the
        declaration stays exactly as written.
        """
        version = cls.version_of(spec)
        if version is None:
            return
        if isinstance(table[key], str):
            table[key] = version
        else:
            cast(InlineTable, table[key])["version"] = version

    @staticmethod
    def version_of(spec: Toml) -> str | None:
        """The version constraint a resolved spec carries, or `None` when it has none."""
        if isinstance(spec, Mapping):
            version = spec.get("version")
            return version if isinstance(version, str) else None
        return spec if isinstance(spec, str) else None
