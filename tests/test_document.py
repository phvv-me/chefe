import pytest
import tomlkit
from hypothesis import given
from hypothesis import strategies as st

from chefe.base import Toml
from chefe.errors import ChefeError
from chefe.manifest import Document
from chefe.utils import satisfied

from .conftest import document_from_toml, version_maps
from .strategies import PACKAGES, VERSIONS, sources

# A Document edit can target any source and any (or no) named env.
ENVS = st.sampled_from(["", "serving", "dev"])


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


@pytest.mark.parametrize(
    ("declared", "resolved", "expected"),
    [
        # A bare-string version is replaced wholesale by the resolved version.
        ({"ruff": ">=0.6"}, {"ruff": {"version": "0.9.0"}}, {"ruff": "0.9.0"}),
        # Bumping an inline-table spec keeps its index alias, replacing only the version.
        (
            {"torch": {"version": ">=1.0", "index": "pytorch"}},
            {"torch": {"version": "2.5.0"}},
            {"torch": {"version": "2.5.0", "index": "pytorch"}},
        ),
        # A versionless (path/git/url) resolved spec has nothing to bump, so it stays as written.
        (
            {"lote": {"path": "../packages/lote"}},
            {"lote": {"path": "../x"}, "kernel": {"url": "https://example.com/k.whl"}},
            {"lote": {"path": "../packages/lote"}, "kernel": {"url": "https://example.com/k.whl"}},
        ),
    ],
    ids=["bare-string", "inline-keeps-index", "versionless-untouched-and-added"],
)
def test_merge_bumps_in_place_preserving_shape(
    declared: dict[str, Toml],
    resolved: dict[str, Toml],
    expected: dict[str, Toml],
) -> None:
    """merge bumps a declared dep's version while keeping its written shape, skips versionless
    specs that carry no version, and adds genuinely new deps verbatim."""
    with document_from_toml() as document:
        table = document.table(["python", "deps"])
        for name, value in declared.items():
            if isinstance(value, str):
                table[name] = value
            else:
                inline = tomlkit.inline_table()
                inline.update(value)
                table[name] = inline

        document.merge(table, resolved)

        assert {
            name: dict(value) if not isinstance(value, str) else value
            for name, value in table.items()
        } == expected


@pytest.mark.parametrize(
    ("manifest_body", "pixi_doc", "checks"),
    [
        # Base scope: conda `[dependencies]` folds into `[deps]`, bumping and adding.
        (
            '[deps]\npython = ">=3.11"\n',
            {"dependencies": {"python": "3.12.0", "numpy": "2.0.0"}},
            [(["deps"], "python", "3.12.0"), (["deps"], "numpy", "2.0.0")],
        ),
        # Base Python: `[pypi-dependencies]` folds into `[python.deps]`.
        (
            '[python.deps]\nruff = ">=0.6"\n',
            {"pypi-dependencies": {"ruff": {"version": "0.9.0"}}},
            [(["python", "deps"], "ruff", "0.9.0")],
        ),
        # A named feature N folds into `[envs.N...]`.
        (
            '[envs.serving.python.deps]\nvllm = ">=0.6"\n',
            {"feature": {"serving": {"pypi-dependencies": {"vllm": "0.7.0"}}}},
            [(["envs", "serving", "python", "deps"], "vllm", "0.7.0")],
        ),
        # A root target folds into `[on.<platform>]`.
        (
            '[on.linux-64.deps]\ncupy = ">=13"\n',
            {"target": {"linux-64": {"dependencies": {"cupy": "13.2.0"}}}},
            [(["on", "linux-64", "deps"], "cupy", "13.2.0")],
        ),
        # The pixi `dev` feature comes from `[dev]`, so it folds there, never `[envs.dev]`.
        (
            '[dev.deps]\nruff = "*"\n',
            {"feature": {"dev": {"dependencies": {"ruff": ">=0.9,<0.10"}}}},
            [(["dev", "deps"], "ruff", ">=0.9,<0.10")],
        ),
        # A target nested inside a feature folds into that env's `[on.<platform>]` overlay.
        (
            '[envs.serving.on.linux-64.deps]\nvllm = ">=0.19"\n',
            {
                "feature": {
                    "serving": {
                        "target": {"linux-64": {"dependencies": {"vllm": ">=0.19.1,<0.20"}}}
                    }
                }
            },
            [(["envs", "serving", "on", "linux-64", "deps"], "vllm", ">=0.19.1,<0.20")],
        ),
    ],
    ids=["base-conda", "base-python", "feature", "root-target", "dev-feature", "feature-target"],
)
def test_pull_maps_each_pixi_scope_to_its_manifest_path(
    manifest_body: str,
    pixi_doc: dict[str, Toml],
    checks: list[tuple[list[str], str, str]],
) -> None:
    """pull routes each pixi scope (base, feature, target, dev feature, feature-target) back into
    the manifest path that declares it, bumping the declared version in place."""
    with document_from_toml(f'[workspace]\nname = "w"\n\n{manifest_body}') as document:
        document.pull(pixi_doc)
        for path, key, expected in checks:
            assert document.table(path)[key] == expected
        # The dev feature never fabricates an `[envs.dev]` table.
        if "dev" in pixi_doc.get("feature", {}):
            assert "envs" not in document.doc


def test_pull_bumps_family_scope_instead_of_duplicating_concrete_platform() -> None:
    """A dep declared under a family selector is bumped there when pixi resolves it for a
    concrete platform, instead of being duplicated into a new `[on.<platform>]` table.

    Kept as a standalone repro: this is the family-scope duplication regression."""
    with document_from_toml(
        """
        [workspace]
        name = "w"

        [on.linux.deps]
        cupy = ">=13"

        [on.osx.python.deps]
        torch = ">=2.11"
        """
    ) as document:
        document.pull(
            {
                "target": {
                    "linux-64": {"dependencies": {"cupy": ">=14.1.1,<15"}},
                    "osx-arm64": {"pypi-dependencies": {"torch": ">=2.11.0, <3"}},
                }
            }
        )
        assert document.table(["on", "linux", "deps"])["cupy"] == ">=14.1.1,<15"
        assert document.table(["on", "osx", "python", "deps"])["torch"] == ">=2.11.0, <3"
        assert "linux-64" not in document.doc.get("on", {})
        assert "osx-arm64" not in document.doc.get("on", {})


def test_save_refuses_an_invalid_manifest() -> None:
    """save() validates the document first, so a writer can never wedge the workspace."""
    with document_from_toml() as document:
        before = document.path.read_text()
        document.table(["envs", "dev", "deps"])["ruff"] = "*"
        with pytest.raises(ChefeError, match="reserved"):
            document.save()
        assert document.path.read_text() == before


@pytest.mark.parametrize(
    ("body", "removed", "remaining_path", "remaining_key", "survives"),
    [
        # Removing a runtime from `[deps]` drops its matching runtime-keyed table whole.
        (
            '[deps]\nrust = "*"\n\n[rust.deps]\nripgrep = "*"\n',
            ["rust"],
            ["rust"],
            None,
            None,
        ),
        # A toolchain table with only `manager` and `[dev.deps]` is still removed with its runtime,
        # so the manifest never strands a table the validator would reject; structural tables stay.
        (
            '[deps]\nnodejs = "*"\n\n[nodejs]\nmanager = "pnpm"\n\n'
            '[nodejs.dev.deps]\nprettier = "*"\n',
            ["nodejs"],
            ["nodejs"],
            None,
            "workspace",
        ),
        # `deps = { ... }` written inline is still a deps table for remove.
        (
            '[deps]\nnodejs = "*"\n\n[nodejs]\ndeps = { leftpad = "*" }\n',
            ["leftpad"],
            ["nodejs", "deps"],
            "leftpad",
            None,
        ),
        # An env sharing a removed package's name is a scope, not a toolchain table: the dep
        # goes, the `[envs.serving]` table stays.
        (
            '[deps]\npython = "*"\n\n[envs.serving.deps]\nserving = "*"\n',
            ["serving"],
            ["envs", "serving"],
            "serving",
            "envs",
        ),
        # `[dev]` is structural: removing a package named `dev` never deletes the dev tooling.
        (
            '[deps]\ndev = "*"\n\n[dev.deps]\nruff = "*"\n',
            ["dev"],
            ["dev", "deps"],
            "dev",
            "dev",
        ),
        # A platform overlay sharing a removed package's name survives the same way.
        (
            '[deps]\npython = "*"\n\n[on.linux.deps]\nlinux = "*"\n',
            ["linux"],
            ["on", "linux"],
            "linux",
            "on",
        ),
        # An env-scoped toolchain table is still dropped with its runtime.
        (
            '[deps]\npython = "*"\n\n[envs.web.deps]\nnodejs = "*"\n\n'
            '[envs.web.nodejs.deps]\nprettier = "*"\n',
            ["nodejs"],
            ["envs", "web"],
            "nodejs",
            "envs",
        ),
    ],
    ids=[
        "runtime-table",
        "table-without-direct-deps",
        "inline-deps-table",
        "env-name-collision",
        "dev-name-collision",
        "platform-name-collision",
        "env-scoped-runtime-table",
    ],
)
def test_remove_drops_deps_and_runtime_tables(
    body: str,
    removed: list[str],
    remaining_path: list[str],
    remaining_key: str | None,
    survives: str | None,
) -> None:
    """remove pops a package from every dep table (section or inline) and drops a runtime-keyed
    toolchain table whose runtime is removed, while never touching structural tables."""
    with document_from_toml(f'[workspace]\nname = "w"\n\n{body}') as document:
        assert document.remove(tuple(removed)) == removed
        if remaining_key is None:
            assert remaining_path[0] not in document.doc
        else:
            assert remaining_key not in document.doc[remaining_path[0]][remaining_path[1]]
        if survives is not None:
            assert survives in document.doc


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
def test_satisfied_wildcard_self_and_unparsable(version: str) -> None:
    """`*`/`""` accept anything, a version satisfies its own `==`, and an unparsable spec,
    version, or a pinless (`None`) install is treated as satisfied (display-only; pixi is
    the real gate)."""
    assert satisfied("*", version)
    assert satisfied("", version)
    assert satisfied(f"=={version}", version)
    assert satisfied("not-a-spec", version)
    assert satisfied(">=1.0", "not-a-version")
    assert satisfied(">=1.0", None)
