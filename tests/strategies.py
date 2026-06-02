from __future__ import annotations

import string
import tempfile
from pathlib import Path

from hypothesis import strategies as st

from chefe.manifest import Document, Env, Header, Manifest, PyPI, Registry, Runtime, Scope, Spec

# Leaf alphabets come from stdlib `string`; the structure is derived from the pydantic
# models themselves via `st.builds`, so adding a field to a model widens these strategies
# without touching this file beyond the leaf each new field needs.

# A package name pixi/uv accepts and that survives `Document.normalize` round-trips.
PACKAGES = st.text(string.ascii_lowercase + string.digits + "-_", min_size=1, max_size=10).filter(
    lambda name: name[0] in string.ascii_lowercase
)

# A few realistic version constraints plus the wildcard.
VERSIONS = st.sampled_from(["*", ">=1.0", "==2.3.4", ">=3.11,<4", "~=1.4", "1.2.3"])

# Pixi platform selectors the manifest may overlay on.
PLATFORMS = st.sampled_from(["osx-arm64", "osx-64", "linux-64", "linux-aarch64", "win-64"])

# The non-conda ecosystems that own a `[<eco>.deps]` table, read from the runtime enum.
ECOSYSTEMS = tuple(Runtime.__members__)  # ("pypi", "npm", "cargo", "gem")

# Every dep source an `add` can target, conda first (the bare `[deps]` table).
SOURCES_LIST = ["conda", *ECOSYSTEMS]


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


def documents() -> st.SearchStrategy[Document]:
    """A fresh `Document` over a header-only `chefe.toml`, isolated per drawn example.

    Each draw gets its own temp directory so property examples never share document state;
    Hypothesis owns the lifetime, so no manual cleanup is needed within a property run.
    """

    def make(token: int) -> Document:
        path = Path(tempfile.mkdtemp(prefix="chefe-")) / "chefe.toml"
        path.write_text('[workspace]\nname = "w"\n')
        return Document(path)

    return st.builds(make, st.integers())


# `Spec` is the leaf every registry/scope dep map holds; registering it lets `st.builds`
# fill any `dict[str, Spec]` field by name without each caller re-specifying the value.
st.register_type_strategy(Spec, specs())


def dep_maps() -> st.SearchStrategy[dict[str, Spec]]:
    """A `name -> Spec` table; names are unique so none collide under normalization."""
    return st.dictionaries(PACKAGES, specs(), max_size=4)


def registries(*, with_indexes: bool = True) -> st.SearchStrategy[Registry]:
    """A non-conda registry; the pypi flavor may also carry named indexes."""
    plain = st.builds(Registry, deps=dep_maps())
    if not with_indexes:
        return plain
    indexes = st.dictionaries(
        st.sampled_from(["pytorch", "internal"]),
        st.just("https://example.com/whl"),
        max_size=2,
    )
    return st.one_of(plain, st.builds(PyPI, deps=dep_maps(), indexes=indexes))


def scopes() -> st.SearchStrategy[Scope]:
    """A `Scope`: conda `deps` plus optional per-ecosystem registries, built from the model."""
    return st.builds(
        Scope,
        deps=dep_maps(),
        pypi=st.builds(PyPI, deps=dep_maps()),
        cargo=st.builds(Registry, deps=dep_maps()),
        npm=st.builds(Registry, deps=dep_maps()),
        gem=st.builds(Registry, deps=dep_maps()),
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
        pypi=st.builds(PyPI, deps=dep_maps()),
        cargo=st.builds(Registry, deps=dep_maps()),
        npm=st.builds(Registry, deps=dep_maps()),
        gem=st.builds(Registry, deps=dep_maps()),
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
        pypi=st.builds(PyPI, deps=dep_maps()),
        cargo=st.builds(Registry, deps=dep_maps()),
        npm=st.builds(Registry, deps=dep_maps()),
        gem=st.builds(Registry, deps=dep_maps()),
        on=st.dictionaries(PLATFORMS, scopes(), max_size=2),
        envs=st.dictionaries(PACKAGES, envs(), max_size=2),
    )
