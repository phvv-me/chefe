from collections.abc import Mapping
from pathlib import Path
from typing import cast

import tomlkit
from tomlkit import TOMLDocument
from tomlkit.items import InlineTable, Table

from ..base import Toml


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
    def dep_tables(cls, node: Mapping[str, Toml]) -> list[Table]:
        """Every nested `deps` table in ``node``."""
        tables: list[Table] = []
        for key, value in node.items():
            if key == "deps" and isinstance(value, Table):
                tables.append(value)
            elif isinstance(value, Mapping):
                tables.extend(cls.dep_tables(value))
        return tables

    def save(self) -> None:
        """Write the document back to disk."""
        self.path.write_text(tomlkit.dumps(self.doc))

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

    def remove_source_tables(self, node: Table | TOMLDocument, packages: tuple[str, ...]) -> None:
        """Remove runtime-keyed source tables when their runtime package is removed."""
        targets = {self.normalize(package) for package in packages}
        for key, value in tuple(node.items()):
            if not isinstance(value, Table):
                continue
            if self.normalize(key) in targets and "deps" in value:
                node.pop(key, None)
            else:
                self.remove_source_tables(value, packages)

    def pull(self, pixi_doc: Mapping[str, Toml]) -> None:
        """Fold pixi's resolved conda + Python deps from a `pixi.toml` dict back into the manifest.

        Walks the base scope, each env (feature) and each platform (target), bumping declared
        versions and adding what pixi added, while keeping comments and index aliases intact.
        """
        scopes: list[tuple[tuple[str, ...], list[str]]] = [((), [])]
        scopes += [(("feature", n), ["envs", n]) for n in self.dig(pixi_doc, "feature")]
        scopes += [(("target", p), ["on", p]) for p in self.dig(pixi_doc, "target")]
        for at, dest in scopes:
            for source, sub in (
                ("dependencies", ["deps"]),
                ("pypi-dependencies", ["python", "deps"]),
            ):
                resolved = self.dig(pixi_doc, *at, source)
                if resolved:
                    self.merge(self.table([*dest, *sub]), resolved)

    def merge(self, table: Table, resolved: Mapping[str, Toml]) -> None:
        """Bump versions of deps already in ``table`` (keeping index/source); add what's new."""
        declared = {self.normalize(name): name for name in table}
        for name, spec in resolved.items():
            version = spec["version"] if isinstance(spec, Mapping) else spec
            key = declared.get(self.normalize(name))
            if key is None:
                table[name] = spec
            elif isinstance(table[key], str):
                table[key] = version
            else:
                cast(InlineTable, table[key])["version"] = version
