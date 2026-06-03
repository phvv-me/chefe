from __future__ import annotations

import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import tomlkit
from hypothesis import given
from hypothesis import strategies as st

from chefe.base import Toml
from chefe.manifest import Document
from chefe.utils import satisfied

from .strategies import PACKAGES, VERSIONS, sources

# A Document edit can target any source and any (or no) named env.
ENVS = st.sampled_from(["", "serving", "dev"])


def version_maps(versions: st.SearchStrategy[str]) -> st.SearchStrategy[dict[str, str]]:
    """Dependency version maps whose keys stay unique after `Document.normalize`."""
    return st.lists(PACKAGES, max_size=4, unique_by=Document.normalize).flatmap(
        lambda names: st.fixed_dictionaries({name: versions for name in names})
    )


@contextmanager
def document_from_toml(text: str = '[workspace]\nname = "w"\n') -> Iterator[Document]:
    """Create an on-disk editable manifest from TOML text for one test example."""
    with tempfile.TemporaryDirectory(prefix="chefe-") as root:
        path = Path(root) / "chefe.toml"
        path.write_text(text)
        yield Document(path)


@given(
    source=sources(),
    env=ENVS,
    packages=st.lists(PACKAGES, min_size=1, max_size=4, unique_by=Document.normalize),
    spec=VERSIONS,
)
def test_add_then_remove_is_identity(
    source: str,
    env: str,
    packages: list[str],
    spec: str,
) -> None:
    """add(pkgs) then remove(pkgs) restores the document, and remove reports what it dropped."""
    with document_from_toml() as document:
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
    declared=version_maps(VERSIONS),
    resolved=version_maps(st.sampled_from(["9.9.9", "10.0.0"])),
)
def test_pull_is_monotonic(declared: dict[str, str], resolved: dict[str, str]) -> None:
    """merge bumps existing keys and adds new ones, never dropping a declared key."""
    with document_from_toml() as document:
        document.add("conda", "", tuple(declared), "*")
        for name, spec in declared.items():
            document.table(["deps"])[name] = spec
        table = document.table(["deps"])
        before = set(table.keys())

        document.merge(table, dict(resolved))

        assert before <= set(table.keys())  # nothing dropped
        for name, version in resolved.items():
            match = next(
                (k for k in table if Document.normalize(k) == Document.normalize(name)), None
            )
            assert match is not None
            assert table[match] == version  # bumped or added at the resolved version


@given(version=st.sampled_from(["9.9.9", "10.0.0"]))
def test_pull_preserves_index_alias_on_inline_specs(version: str) -> None:
    """Bumping an inline-table spec keeps its index alias, replacing only the version."""
    with document_from_toml() as document:
        table = document.table(["python", "deps"])
        inline = tomlkit.inline_table()
        inline.update({"version": ">=1.0", "index": "pytorch"})
        table["torch"] = inline

        document.merge(table, {"torch": {"version": version}})

        assert table["torch"]["index"] == "pytorch"
        assert table["torch"]["version"] == version


def test_pull_folds_base_env_and_target(document: Document) -> None:
    """pull walks the base scope, each feature and each target, bumping and adding deps."""
    document.table(["deps"])["python"] = ">=3.11"
    document.table(["python", "deps"])["ruff"] = ">=0.6"
    document.table(["envs", "serving", "python", "deps"])["vllm"] = ">=0.6"
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
    assert document.table(["python", "deps"])["ruff"] == "0.9.0"
    assert document.table(["envs", "serving", "python", "deps"])["vllm"] == "0.7.0"
    assert document.table(["on", "linux-64", "deps"])["cupy"] == "13.2.0"


def test_remove_runtime_package_drops_matching_toolchain_table() -> None:
    """Removing a runtime from `[deps]` removes the matching runtime-keyed table."""
    with document_from_toml(
        """
        [workspace]
        name = "w"

        [deps]
        rust = "*"

        [rust.deps]
        ripgrep = "*"
        """
    ) as document:
        assert document.remove(("rust",)) == ["rust"]
        assert "rust" not in document.doc


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
