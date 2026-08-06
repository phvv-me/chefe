from collections.abc import Mapping

from tomlkit.items import AbstractTable

from ...core import Toml, platform_scopes


def dep_path(source: str, *, env: str) -> list[str]:
    """The deps table path for ``source`` (conda = bare `[deps]`), nested under ``env``."""
    base = ["deps"] if source == "conda" else [source, "deps"]
    return ["envs", env, *base] if env else base


def dig(data: Mapping[str, Toml], *keys: str) -> Mapping[str, Toml]:
    """Walk ``keys`` into a nested table, returning the leaf mapping (or empty)."""
    node: Toml | Mapping[str, Toml] = data
    for key in keys:
        node = node.get(key, {}) if isinstance(node, Mapping) else {}
    return node if isinstance(node, Mapping) else {}


def normalize(name: str) -> str:
    """Canonical package key for matching (case- and `_`/`-`-insensitive)."""
    return name.lower().replace("_", "-")


def version_of(spec: Toml) -> str | None:
    """The version constraint a resolved spec carries, or `None` when it has none."""
    if isinstance(spec, Mapping):
        version = spec.get("version")
        return version if isinstance(version, str) else None
    return spec if isinstance(spec, str) else None


def declared_key(table: Mapping[str, Toml], name: str) -> str | None:
    """The key in ``table`` declaring ``name``, matched through `normalize` (or `None`)."""
    target = normalize(name)
    return next((key for key in table if normalize(key) == target), None)


def dep_tables(node: Mapping[str, Toml]) -> list[AbstractTable]:
    """Every nested `deps` table in ``node``, whether a section or an inline table."""
    tables: list[AbstractTable] = []
    for key, value in node.items():
        if key == "deps" and isinstance(value, AbstractTable):
            tables.append(value)
        elif isinstance(value, Mapping):
            tables.extend(dep_tables(value))
    return tables


def pixi_scopes(pixi_doc: Mapping[str, Toml]) -> list[tuple[tuple[str, ...], list[list[str]]]]:
    """Each pixi scope paired with the manifest paths that can declare its deps.

    The `dev` feature is compiled from the manifest's `[dev]` table, so it folds back there
    rather than into a fabricated `[envs.dev]`.
    """
    scopes: list[tuple[tuple[str, ...], list[list[str]]]] = [((), [[]])]
    for name in dig(pixi_doc, "feature"):
        dest = ["dev"] if name == "dev" else ["envs", name]
        scopes.append(((("feature", name)), [dest]))
        for plat in dig(pixi_doc, "feature", name, "target"):
            scopes.append(
                (
                    ("feature", name, "target", plat),
                    [[*dest, "on", key] for key in platform_scopes(plat)],
                )
            )
    for plat in dig(pixi_doc, "target"):
        scopes.append((("target", plat), [["on", key] for key in platform_scopes(plat)]))
    return scopes
