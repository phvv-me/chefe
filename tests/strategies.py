from __future__ import annotations

import string

from hypothesis import strategies as st

from chefe.manifest import (
    Document,
    Env,
    Header,
    Manifest,
    Scope,
    Spec,
)

# Leaf alphabets come from stdlib `string`; the structure is derived from the pydantic
# models themselves via `st.builds`, so adding a field to a model widens these strategies
# without touching this file beyond the leaf each new field needs.

# A package name pixi/uv accepts and that survives `Document.normalize` round-trips.
PACKAGES = st.text(string.ascii_lowercase + string.digits + "-_", min_size=1, max_size=10).filter(
    lambda name: name[0] in string.ascii_lowercase
)

# `default` is the implicit environment name, so users cannot define `[envs.default]`.
ENV_NAMES = PACKAGES.filter(lambda name: name != "default")

# A few realistic version constraints plus the wildcard.
VERSIONS = st.sampled_from(["*", ">=1.0", "==2.3.4", ">=3.11,<4", "~=1.4", "1.2.3"])

# Pixi platform selectors the manifest may overlay on.
PLATFORMS = st.sampled_from(["osx-arm64", "osx-64", "linux-64", "linux-aarch64", "win-64"])

# Top-level schema keys that cannot also be runtime-keyed toolchain tables.
RESERVED_TABLES = frozenset(Manifest.model_fields) | {"conda"}


def toolchain_names() -> st.SearchStrategy[str]:
    """A TOML-safe runtime/toolchain name that is not a reserved manifest table."""
    return PACKAGES.filter(lambda name: name not in RESERVED_TABLES)


def sources() -> st.SearchStrategy[str]:
    """A dependency source: conda or any runtime-keyed toolchain/language."""
    return st.one_of(st.just("conda"), toolchain_names())


def specs() -> st.SearchStrategy[Spec]:
    """A `Spec` in either form: a bare version, or an inline table with index + passthrough.

    Built straight through `Spec.model_validate`, so the bare-string coercion and the
    `FlexModel` extra path are both exercised exactly as a manifest author would hit them.
    """
    bare = VERSIONS.map(Spec.model_validate)
    table = st.fixed_dictionaries(
        {},
        optional={
            "version": VERSIONS,
            "index": st.sampled_from(["pytorch", "internal"]),
            "git": st.just("https://example.com/x.git"),
            "branch": st.sampled_from(["main", "dev"]),
        },
    ).filter(bool)
    return st.one_of(bare, table.map(Spec.model_validate))


# `Spec` is the leaf every registry/scope dep map holds; registering it lets `st.builds`
# fill any `dict[str, Spec]` field by name without each caller re-specifying the value.
st.register_type_strategy(Spec, specs())


def dep_maps() -> st.SearchStrategy[dict[str, Spec]]:
    """A `name -> Spec` table; names are unique so none collide under normalization."""
    return st.lists(PACKAGES, max_size=4, unique_by=Document.normalize).flatmap(
        lambda names: st.fixed_dictionaries({name: specs() for name in names})
    )


def scopes() -> st.SearchStrategy[Scope]:
    """A `Scope`: conda `deps`, built from the model."""
    return st.builds(
        Scope,
        deps=dep_maps(),
    )


def headers() -> st.SearchStrategy[Header]:
    """A `[workspace]` header with one or more platforms."""
    return st.builds(
        Header,
        name=PACKAGES,
        platforms=st.lists(PLATFORMS, min_size=1, max_size=3, unique=True),
    )


def envs() -> st.SearchStrategy[Env]:
    """A named environment: a scope plus optional platform overlays and a no-default flag."""
    return st.builds(
        Env,
        deps=dep_maps(),
        on=st.dictionaries(PLATFORMS, scopes(), max_size=2),
        no_default=st.booleans(),
    )


def manifests() -> st.SearchStrategy[Manifest]:
    """A full, valid `Manifest`: header + base scope + platform overlays + named envs.

    Every nested value is itself a model-derived strategy, so overlays and envs reuse the
    exact dep shapes the base scope does and the result always validates.
    """
    return st.builds(
        Manifest,
        workspace=headers(),
        deps=dep_maps(),
        on=st.dictionaries(PLATFORMS, scopes(), max_size=2),
        envs=st.dictionaries(ENV_NAMES, envs(), max_size=2),
    )
