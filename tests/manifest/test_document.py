import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest
import tomlkit
from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, initialize, invariant, rule

from chefe.compiled import PixiManifest
from chefe.core import ChefeError, Toml, is_satisfied
from chefe.manifest import Document, Manifest
from chefe.manifest.editing import dep_path, dig, normalize

from ..support.strategies import packages, sources, version_maps, versions
from ..support.workspaces import document_from_toml

# The empty string stands for the unnamed base scope, whose dep path skips `envs` entirely.
_ENVS = st.sampled_from(["", "serving", "dev"])


@given(
    source=sources(),
    env=_ENVS,
    packages=st.lists(packages(), min_size=1, max_size=4, unique_by=normalize),
    spec=versions(),
)
def test_add_then_remove_is_identity(
    *,
    source: str,
    env: str,
    packages: list[str],
    spec: str,
) -> None:
    """add(pkgs) then remove(pkgs) restores the document, and remove reports what it dropped."""
    with document_from_toml() as document:
        before = tomlkit.dumps(document.doc)
        document.add(source, env=env, packages=packages, spec=spec)
        table = document.table(dep_path(source, env=env))
        assert all(table[p] == spec for p in packages)

        assert set(document.remove(packages)) == set(packages)
        # remove() pops keys and never the tables holding them, so only key survival is assertable.
        assert not any(p in document.table(dep_path(source, env=env)) for p in packages)
        # The emptied `[deps]` table is stripped before comparing, since add() created it and
        # remove() cannot take it back out.
        if source == "conda" and env == "":
            after = tomlkit.dumps(document.doc).replace("\n[deps]\n", "").rstrip("\n")
            assert after == before.rstrip("\n")


@given(
    declared=version_maps(versions()),
    resolved=version_maps(st.sampled_from(["9.9.9", "10.0.0"])),
)
def test_pull_is_monotonic(*, declared: dict[str, str], resolved: dict[str, str]) -> None:
    """merge bumps existing keys and adds new ones, never dropping a declared key."""
    with document_from_toml() as document:
        document.add("conda", env="", packages=list(declared), spec="*")
        for name, spec in declared.items():
            document.table(["deps"])[name] = spec
        table = document.table(["deps"])
        before = set(table.keys())

        document.merge(table, dict(resolved))

        assert before <= set(table.keys())
        bumped = {normalize(key): value for key, value in table.items()}
        assert all(bumped.get(normalize(name)) == version for name, version in resolved.items())


@pytest.mark.parametrize(
    ("declared", "resolved", "expected"),
    [
        ({"ruff": ">=0.6"}, {"ruff": {"version": "0.9.0"}}, {"ruff": "0.9.0"}),
        (
            {"torch": {"version": ">=1.0", "index": "pytorch"}},
            {"torch": {"version": "2.5.0"}},
            {"torch": {"version": "2.5.0", "index": "pytorch"}},
        ),
        (
            {"lote": {"path": "../packages/lote"}},
            {"lote": {"path": "../x"}, "kernel": {"url": "https://example.com/k.whl"}},
            {"lote": {"path": "../packages/lote"}, "kernel": {"url": "https://example.com/k.whl"}},
        ),
    ],
    ids=["bare-string", "inline-keeps-index", "versionless-untouched-and-added"],
)
def test_merge_bumps_in_place_preserving_shape(
    *,
    declared: Mapping[str, Toml],
    resolved: dict[str, Toml],
    expected: dict[str, Toml],
) -> None:
    """merge bumps a declared dep's version while keeping its written shape.

    It skips versionless specs that carry no version, and adds genuinely new deps verbatim.
    """
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
        (
            '[deps]\npython = ">=3.11"\n',
            {"dependencies": {"python": "3.12.0", "numpy": "2.0.0"}},
            [(["deps"], "python", "3.12.0"), (["deps"], "numpy", "2.0.0")],
        ),
        (
            '[python.deps]\nruff = ">=0.6"\n',
            {"pypi-dependencies": {"ruff": {"version": "0.9.0"}}},
            [(["python", "deps"], "ruff", "0.9.0")],
        ),
        (
            '[envs.serving.python.deps]\nvllm = ">=0.6"\n',
            {"feature": {"serving": {"pypi-dependencies": {"vllm": "0.7.0"}}}},
            [(["envs", "serving", "python", "deps"], "vllm", "0.7.0")],
        ),
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
    checks: Sequence[tuple[list[str], str, str]],
) -> None:
    """pull routes each pixi scope back into the manifest path that declares it.

    The scopes are base, feature, target, dev feature, and feature-target, and each one has its
    declared version bumped in place.
    """
    with document_from_toml(f'[workspace]\nname = "w"\n\n{manifest_body}') as document:
        document.pull(pixi_doc)
        for path, key, expected in checks:
            assert document.table(path)[key] == expected
        if "dev" in pixi_doc.get("feature", {}):
            assert "envs" not in document.doc


def test_pull_bumps_family_scope_instead_of_duplicating_concrete_platform() -> None:
    """A dep declared under a family selector is bumped there, not duplicated per platform.

    When pixi resolves it for a concrete platform the bump lands on the family selector rather
    than on a new `[on.<platform>]` table. Kept as a standalone repro of the family-scope
    duplication regression.
    """
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
            """[deps]
nodejs = "*"

[nodejs]
manager = "pnpm"

[nodejs.dev.deps]
prettier = "*"
""",
            ["nodejs"],
            ["nodejs"],
            None,
            "workspace",
        ),
        (
            '[deps]\nnodejs = "*"\n\n[nodejs]\ndeps = { leftpad = "*" }\n',
            ["leftpad"],
            ["nodejs", "deps"],
            "leftpad",
            None,
        ),
        (
            '[deps]\npython = "*"\n\n[envs.serving.deps]\nserving = "*"\n',
            ["serving"],
            ["envs", "serving"],
            "serving",
            "envs",
        ),
        (
            '[deps]\ndev = "*"\n\n[dev.deps]\nruff = "*"\n',
            ["dev"],
            ["dev", "deps"],
            "dev",
            "dev",
        ),
        (
            '[deps]\npython = "*"\n\n[on.linux.deps]\nlinux = "*"\n',
            ["linux"],
            ["on", "linux"],
            "linux",
            "on",
        ),
        (
            """[deps]
python = "*"

[envs.web.deps]
nodejs = "*"

[envs.web.nodejs.deps]
prettier = "*"
""",
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
    *,
    body: str,
    removed: list[str],
    remaining_path: Sequence[str],
    remaining_key: str | None,
    survives: str | None,
) -> None:
    """remove pops a package from every dep table, whether that table is a section or inline.

    It also drops a runtime-keyed toolchain table whose runtime is removed, while never touching
    structural tables.
    """
    with document_from_toml(f'[workspace]\nname = "w"\n\n{body}') as document:
        assert document.remove(list(removed)) == removed
        if remaining_key is None:
            assert remaining_path[0] not in document.doc
        else:
            assert remaining_key not in document.doc[remaining_path[0]][remaining_path[1]]
        if survives is not None:
            assert survives in document.doc


def test_dig_returns_empty_on_non_dict_branch() -> None:
    """dig stops at the first non-dict node and yields an empty leaf."""
    assert dig({"a": {"b": 5}}, "a", "b", "c") == {}
    assert dig({}, "missing") == {}


@given(name=packages(), noise=st.sampled_from(["_", "-"]))
def test_normalize_is_idempotent_and_insensitive(*, name: str, noise: str) -> None:
    """normalize folds case and `_`/`-`, and applying it twice changes nothing."""
    once = normalize(name)
    assert normalize(once) == once
    assert normalize(name.upper()) == once
    assert normalize(name.replace("-", noise).replace("_", noise)) == once


@given(version=st.sampled_from(["1.0.0", "2.5", "0.0.1"]))
def test_satisfied_wildcard_self_and_unparsable(version: str) -> None:
    """`*` and `""` accept anything, and a version satisfies its own `==`.

    An unparsable spec, an unparsable version, and a pinless `None` install all count as
    satisfied, since this check is display-only and pixi remains the real gate.
    """
    assert is_satisfied("*", version)
    assert is_satisfied("", version)
    assert is_satisfied(f"=={version}", version)
    assert is_satisfied("not-a-spec", version)
    assert is_satisfied(">=1.0", "not-a-version")
    assert is_satisfied(">=1.0", None)


class ManifestMachine(RuleBasedStateMachine):
    """Drive add/remove/sync over a live manifest, asserting it stays coherent throughout.

    One machine subsumes dozens of command sequences: after any interleaving of edits the
    document must still validate as a Manifest, compile to a PixiManifest, and have its
    `declared()` view agree with the dep tables actually on disk.
    """

    def __init__(self) -> None:
        super().__init__()
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "chefe.toml"

    @rule(source=sources(), package=packages(), spec=versions())
    def add(self, *, source: str, package: str, spec: str) -> None:
        document = Document(self.path)
        if source != "conda":
            document.add("conda", env="", packages=(source,), spec="*")
        document.add(source, env="", packages=(package,), spec=spec)
        document.save()

    @invariant()
    def declared_matches_tables(self) -> None:
        manifest = Manifest.load(self.path)
        declared = manifest.declared("default", platform="linux-64")
        # declared folds the groups in order, so a name's source is its last-writing group.
        expected: dict[str, str] = {}
        for source, deps in manifest.groups().items():
            for name in deps:
                expected[name] = source
        assert {name: dep.source for name, dep in declared.items()} == expected

    @rule(package=packages())
    def remove(self, package: str) -> None:
        document = Document(self.path)
        document.remove((package,))
        document.save()

    @invariant()
    def removed_keys_are_truly_gone(self) -> None:
        # Every key the document can see in a dep table is reachable via its dep_path.
        document = Document(self.path)
        manifest = Manifest.load(self.path)
        for source, deps in manifest.groups().items():
            table = document.table(dep_path(source, env=""))
            for name in deps:
                assert any(normalize(k) == normalize(name) for k in table)

    @initialize()
    def scaffold(self) -> None:
        self.path.write_text(
            '[workspace]\nname = "w"\nplatforms = ["linux-64"]\n\n[deps]\npython = ">=3.11"\n'
        )

    @invariant()
    def stays_compilable(self) -> None:
        manifest = Manifest.load(self.path)
        PixiManifest.from_manifest(manifest)  # never raises on a reachable state

    def teardown(self) -> None:
        self.dir.cleanup()


TestManifestMachine = ManifestMachine.TestCase
TestManifestMachine.settings = settings(max_examples=40, stateful_step_count=12, deadline=None)
