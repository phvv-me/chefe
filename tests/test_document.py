from __future__ import annotations

import tomlkit
from hypothesis import given
from hypothesis import strategies as st

from chefe.base import Toml
from chefe.manifest import Document
from chefe.utils import satisfied

from .strategies import PACKAGES, SOURCES_LIST, VERSIONS, documents

# A Document edit can target any source and any (or no) named env.
SOURCES = st.sampled_from(SOURCES_LIST)
ENVS = st.sampled_from(["", "serving", "dev"])


@given(
    source=SOURCES,
    env=ENVS,
    packages=st.lists(PACKAGES, min_size=1, max_size=4, unique=True),
    spec=VERSIONS,
    data=st.data(),
)
def test_add_then_remove_is_identity(
    source: str,
    env: str,
    packages: list[str],
    spec: str,
    data: st.DataObject,
) -> None:
    """add(pkgs) then remove(pkgs) restores the document, and remove reports what it dropped."""
    document = data.draw(documents())
    before = tomlkit.dumps(document.doc)
    names = tuple(packages)
    document.add(source, env, names, spec)
    table = document.table(Document.dep_path(source, env))
    assert all(table[p] == spec for p in names)

    removed = document.remove(names)
    assert set(removed) == set(names)
    # Empty intermediate tables may linger, but no declared key survives.
    assert not any(p in document.table(Document.dep_path(source, env)) for p in names)
    # A pure conda add with no env round-trips: ignoring the empty `[deps]` table that
    # may linger, the document returns to exactly what it was before the add.
    if source == "conda" and env == "":
        after = tomlkit.dumps(document.doc).replace("\n[deps]\n", "").rstrip("\n")
        assert after == before.rstrip("\n")


@given(
    declared=st.dictionaries(PACKAGES, VERSIONS, max_size=4),
    resolved=st.dictionaries(PACKAGES, st.sampled_from(["9.9.9", "10.0.0"]), max_size=4),
    data=st.data(),
)
def test_pull_is_monotonic(
    declared: dict[str, str], resolved: dict[str, str], data: st.DataObject
) -> None:
    """merge bumps existing keys and adds new ones, never dropping a declared key."""
    document = data.draw(documents())
    document.add("conda", "", tuple(declared), "*")
    for name, spec in declared.items():
        document.table(["deps"])[name] = spec
    table = document.table(["deps"])
    before = set(table.keys())

    document.merge(table, dict(resolved))

    assert before <= set(table.keys())  # nothing dropped
    for name, version in resolved.items():
        match = next((k for k in table if Document.normalize(k) == Document.normalize(name)), None)
        assert match is not None
        assert table[match] == version  # bumped or added at the resolved version


@given(version=st.sampled_from(["9.9.9", "10.0.0"]), data=st.data())
def test_pull_preserves_index_alias_on_inline_specs(version: str, data: st.DataObject) -> None:
    """Bumping an inline-table spec keeps its index alias, replacing only the version."""
    document = data.draw(documents())
    table = document.table(["pypi", "deps"])
    inline = tomlkit.inline_table()
    inline.update({"version": ">=1.0", "index": "pytorch"})
    table["torch"] = inline

    document.merge(table, {"torch": {"version": version}})

    assert table["torch"]["index"] == "pytorch"
    assert table["torch"]["version"] == version


def test_pull_folds_base_env_and_target(document: Document) -> None:
    """pull walks the base scope, each feature and each target, bumping and adding deps."""
    document.table(["deps"])["python"] = ">=3.11"
    document.table(["pypi", "deps"])["ruff"] = ">=0.6"
    document.table(["envs", "serving", "pypi", "deps"])["vllm"] = ">=0.6"
    document.table(["on", "linux-64", "deps"])["cupy"] = ">=13"

    pixi_doc: dict[str, Toml] = {
        "dependencies": {"python": "3.12.0", "numpy": "2.0.0"},
        "pypi-dependencies": {"ruff": {"version": "0.9.0"}},
        "feature": {"serving": {"pypi-dependencies": {"vllm": "0.7.0"}}},
        "target": {"linux-64": {"dependencies": {"cupy": "13.2.0"}}},
    }
    document.pull(pixi_doc)

    assert document.table(["deps"])["python"] == "3.12.0"  # bumped
    assert document.table(["deps"])["numpy"] == "2.0.0"  # added
    assert document.table(["pypi", "deps"])["ruff"] == "0.9.0"
    assert document.table(["envs", "serving", "pypi", "deps"])["vllm"] == "0.7.0"
    assert document.table(["on", "linux-64", "deps"])["cupy"] == "13.2.0"


def test_dig_returns_empty_on_non_dict_branch() -> None:
    """dig stops at the first non-dict node and yields an empty leaf."""
    assert Document.dig({"a": {"b": 5}}, "a", "b", "c") == {}
    assert Document.dig({}, "missing") == {}


@given(name=PACKAGES, noise=st.sampled_from(["_", "-"]))
def test_normalize_is_idempotent_and_insensitive(name: str, noise: str) -> None:
    """normalize folds case and `_`/`-`, and applying it twice changes nothing."""
    once = Document.normalize(name)
    assert Document.normalize(once) == once
    assert Document.normalize(name.upper()) == once
    assert Document.normalize(name.replace("-", noise).replace("_", noise)) == once


@given(version=st.sampled_from(["1.0.0", "2.5", "0.0.1"]))
def test_satisfied_wildcard_and_self(version: str) -> None:
    """`*` and `""` accept anything, and a version satisfies its own `==` constraint."""
    assert satisfied("*", version)
    assert satisfied("", version)
    assert satisfied(f"=={version}", version)
