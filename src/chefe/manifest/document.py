from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import cast

import tomlkit
from tomlkit import TOMLDocument
from tomlkit.items import InlineTable, Table

from .. import ECOSYSTEMS
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

    @staticmethod
    def dep_in(scope: Toml, ecosystem: str) -> bool:
        """Whether ``scope`` has a `[<ecosystem>.deps]` table (e.g. `[pypi.deps]`)."""
        return (
            isinstance(scope, Mapping)
            and ecosystem in scope
            and isinstance(eco := scope[ecosystem], Mapping)
            and "deps" in eco
        )

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
        tables: list[Table] = []
        for scope in (self.doc, *self.doc.get("envs", {}).values()):
            if "deps" in scope:
                tables.append(cast(Table, scope["deps"]))
            tables += [cast(Table, scope[e]["deps"]) for e in ECOSYSTEMS if self.dep_in(scope, e)]
        return [p for t in tables for p in packages if t.pop(p, None) is not None]

    def pull(self, pixi_doc: Mapping[str, Toml]) -> None:
        """Fold pixi's resolved conda + pypi deps from a `pixi.toml` dict back into the manifest.

        Walks the base scope, each env (feature) and each platform (target), bumping declared
        versions and adding what pixi added, while keeping comments and index aliases intact.
        """
        scopes: list[tuple[tuple[str, ...], list[str]]] = [((), [])]
        scopes += [(("feature", n), ["envs", n]) for n in self.dig(pixi_doc, "feature")]
        scopes += [(("target", p), ["on", p]) for p in self.dig(pixi_doc, "target")]
        for at, dest in scopes:
            for source, sub in (
                ("dependencies", ["deps"]),
                ("pypi-dependencies", ["pypi", "deps"]),
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
