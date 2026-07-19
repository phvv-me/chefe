from collections.abc import Callable
from pathlib import Path

import pytest
from packaging.requirements import Requirement

from chefe.errors import ChefeError
from chefe.manager import PackageManager
from chefe.manifest import Manifest, find_manifest
from chefe.manifest.pyproject import Sources, group, manifest_body, tool_table

# A pyproject that exercises the whole ownership split: `[project.dependencies]` owns runtime deps
# (routed to conda and git by `[tool.chefe.sources]`), `[dependency-groups]` owns dev tools (with a
# PEP 735 include), and `[tool.chefe.conda]` adds the interpreter that has no PEP 508 form.
PYPROJECT = """
[project]
name = "demo"
version = "9.9.9"
dependencies = [
  "sqlalchemy[asyncio]>=2.1.0b3,<3",
  "httpx>=0.28.1,<0.29",
  "patos[sql]>=0.0.9,<0.1",
  "torch>=2.6",
]

[dependency-groups]
dev = ["ruff>=0.6", "ty==0.0.59", {include-group = "test"}]
test = ["pytest>=9", "asyncpg-stubs>=0.31"]

[tool.chefe.workspace]
platforms = ["linux-64"]

[tool.chefe.conda]
python = ">=3.14"

[tool.chefe.sources]
patos = { provider = "git", git = "https://github.com/phvv-me/patos", branch = "main" }
torch = { provider = "conda", package = "pytorch" }
"""


def write_pyproject(root: Path, text: str = PYPROJECT) -> Path:
    """Drop a `pyproject.toml` under ``root`` and return its path."""
    path = root / "pyproject.toml"
    path.write_text(text)
    return path


def test_find_manifest_prefers_pyproject_with_a_chefe_table(tmp_path: Path) -> None:
    """A `pyproject.toml` carrying `[tool.chefe]` is the manifest, even beside a `chefe.toml`."""
    write_pyproject(tmp_path)
    (tmp_path / "chefe.toml").write_text('[workspace]\nname = "other"\n')
    assert find_manifest(tmp_path) == tmp_path / "pyproject.toml"


def test_find_manifest_falls_back_to_chefe_toml_without_a_chefe_table(tmp_path: Path) -> None:
    """A `pyproject.toml` with no `[tool.chefe]` (a monorepo root) defers to the sibling file."""
    write_pyproject(tmp_path, '[project]\nname = "demo"\n\n[tool.ruff]\nline-length = 99\n')
    (tmp_path / "chefe.toml").write_text('[workspace]\nname = "root"\n')
    assert find_manifest(tmp_path) == tmp_path / "chefe.toml"


def test_find_manifest_returns_none_when_absent(tmp_path: Path) -> None:
    """A directory with neither manifest resolves to `None` so `chefe init` can scaffold there."""
    assert find_manifest(tmp_path) is None


def test_find_manifest_takes_a_standalone_chefe_toml(tmp_path: Path) -> None:
    """A workspace with only a `chefe.toml` and no `pyproject.toml` resolves to that file."""
    (tmp_path / "chefe.toml").write_text('[workspace]\nname = "w"\n')
    assert find_manifest(tmp_path) == tmp_path / "chefe.toml"


def test_tool_table_ignores_a_non_mapping_tool(tmp_path: Path) -> None:
    """A `pyproject.toml` whose `tool` is not a table yields an empty mapping, never a crash."""
    path = write_pyproject(tmp_path, 'tool = 5\n[project]\nname = "demo"\n')
    assert tool_table(path) == {}


@pytest.mark.parametrize(
    ("requirement", "table", "expected"),
    [
        ("torch>=2.6", {"provider": "conda", "package": "pytorch"}, (True, "pytorch", ">=2.6")),
        ("widget>=1", {"provider": "conda"}, (True, "widget", ">=1")),
        ("bare", {"provider": "conda"}, (True, "bare", "*")),
        (
            "patos[sql]>=0.0.9",
            {"provider": "git", "git": "u", "branch": "main"},
            (False, "patos", {"git": "u", "branch": "main", "extras": ["sql"]}),
        ),
        (
            "tool",
            {"provider": "path", "path": ".", "editable": True},
            (False, "tool", {"path": ".", "editable": True}),
        ),
        ("boxed[b,a]>=3", None, (False, "boxed", {"version": ">=3", "extras": ["a", "b"]})),
        ("pinned>=1,<2", None, (False, "pinned", "<2,>=1")),
        ("plain", None, (False, "plain", "*")),
    ],
    ids=[
        "conda-rename",
        "conda-plain",
        "conda-bare",
        "git",
        "path",
        "pypi-extras",
        "pypi",
        "bare",
    ],
)
def test_sources_route(
    requirement: str, table: dict[str, object] | None, expected: tuple[bool, str, object]
) -> None:
    """Each provider routes to the right pixi table, keeping version, extras, or its own source."""
    sources = Sources({requirement.split("[")[0].split(">")[0]: table} if table else {})
    assert sources.route(Requirement(requirement)) == expected


def test_sources_skips_a_non_table_entry() -> None:
    """A routing entry that is not a table is ignored, so its dep stays a plain PyPI dep."""
    sources = Sources({"foo": "bar", "torch": {"provider": "conda"}})
    assert sources.route(Requirement("foo>=1")) == (False, "foo", ">=1")


@pytest.mark.parametrize(
    ("groups", "expected"),
    [
        ({"dev": ["a", "b"]}, ["a", "b"]),
        ({"dev": ["a", {"include-group": "extra"}], "extra": ["b"]}, ["a", "b"]),
        ({}, []),
        ({"dev": "oops"}, []),
        ({"dev": [{"include-group": "dev"}]}, []),
    ],
    ids=["flat", "include", "missing", "non-list", "cycle"],
)
def test_group_flattens_pep735(groups: dict[str, object], expected: list[str]) -> None:
    """A dependency group flattens to its requirements, following includes without a cycle."""
    assert group(groups, "dev") == expected


def test_manifest_body_splits_deps_across_conda_and_pypi() -> None:
    """`[project]` and `[dependency-groups]` deps inherit and route per `[tool.chefe.sources]`."""
    manifest = Manifest.from_pyproject(PYPROJECT)
    assert manifest.workspace.name == "demo" and manifest.workspace.version == "9.9.9"
    # conda-only interpreter plus the torch->pytorch conda route land in `[deps]`
    assert manifest.deps["python"].version == ">=3.14"
    assert manifest.deps["pytorch"].version == ">=2.6"
    pypi = manifest.python().deps
    assert pypi["httpx"].version == "<0.29,>=0.28.1"
    assert (pypi["sqlalchemy"].model_extra or {})["extras"] == ["asyncio"]
    # the git route keeps the source and the extras, and drops the (meaningless) git version
    patos = pypi["patos"].model_extra or {}
    assert patos["git"] == "https://github.com/phvv-me/patos" and patos["branch"] == "main"
    assert patos["extras"] == ["sql"]


def test_manifest_body_reads_the_dev_group_with_includes() -> None:
    """`[dependency-groups].dev` (with its include) becomes the dev feature's Python deps."""
    dev = Manifest.from_pyproject(PYPROJECT).dev.toolchains()["python"].deps
    assert dev["ty"].version == "==0.0.59"
    assert set(dev) == {"ruff", "ty", "pytest", "asyncpg-stubs"}


def test_manifest_body_routes_a_dev_dependency_to_conda() -> None:
    """A `[tool.chefe.sources]` conda route on a dev-group dep lands it in the dev conda table."""
    text = (
        '[project]\nname = "demo"\n\n'
        '[dependency-groups]\ndev = ["mkl>=2024"]\n\n'
        '[tool.chefe.workspace]\nplatforms = ["linux-64"]\n\n'
        '[tool.chefe.conda]\npython = ">=3.14"\n\n'
        '[tool.chefe.sources]\nmkl = { provider = "conda" }\n'
    )
    assert manifest_body(text)["dev"]["deps"] == {"mkl": ">=2024"}


def test_manifest_body_self_installs_the_package_editable() -> None:
    """The package installs itself editable so it imports and its own deps resolve."""
    demo = (Manifest.from_pyproject(PYPROJECT).python().deps["demo"].model_extra) or {}
    assert demo["path"] == "." and demo["editable"] is True


def test_manifest_body_keeps_a_python_options_table_and_omits_conda_when_none() -> None:
    """A `[tool.chefe.python]` options table survives; with no conda route `[deps]` is omitted."""
    text = (
        '[project]\nname = "demo"\ndependencies = ["httpx>=0.28"]\n\n'
        '[tool.chefe.workspace]\nplatforms = ["linux-64"]\n\n'
        '[tool.chefe.python.dependency-overrides]\nsqlalchemy = ">=2.1.0b3"\n'
    )
    body = manifest_body(text)
    assert "deps" not in body  # nothing routed to conda
    python = body["python"]
    assert python["dependency-overrides"] == {"sqlalchemy": ">=2.1.0b3"}  # options preserved
    assert "httpx" in python["deps"] and "demo" in python["deps"]


def test_from_pyproject_keeps_an_explicit_workspace_name_and_omits_absent_version() -> None:
    """An explicit `[tool.chefe.workspace]` name wins, and a project with no version keeps none."""
    text = (
        '[project]\nname = "demo"\n\n'
        '[tool.chefe.workspace]\nname = "chosen"\nplatforms = ["linux-64"]\n\n'
        '[tool.chefe.conda]\npython = ">=3.14"\n'
    )
    manifest = Manifest.from_pyproject(text)
    assert manifest.workspace.name == "chosen"
    assert manifest.workspace.version == "0.1.0"  # Header default, since [project] set none


def test_from_pyproject_without_a_project_adds_no_python_deps() -> None:
    """With no `[project]` the manifest names itself in `[tool.chefe]` and adds no Python deps."""
    manifest = Manifest.from_pyproject(
        '[tool.chefe.workspace]\nname = "w"\nplatforms = ["linux-64"]\n'
    )
    assert manifest.workspace.name == "w"
    assert manifest.python().deps == {}


def test_load_dispatches_pyproject_and_manager_discovers_it(tmp_path: Path) -> None:
    """A `PackageManager` over a pyproject workspace loads it and syncs a pixi manifest."""
    write_pyproject(tmp_path)
    manager = PackageManager(tmp_path)
    assert manager.manifest == tmp_path / "pyproject.toml"
    assert manager.load().workspace.name == "demo"
    manager.sync()
    compiled = manager.pixi.manifest.read_text()
    assert "pytorch" in compiled and "demo" in compiled


def test_discover_walks_up_to_a_pyproject_workspace(tmp_path: Path) -> None:
    """Running chefe from a subdirectory finds the pyproject manifest above it, like git."""
    write_pyproject(tmp_path)
    nested = tmp_path / "src" / "pkg"
    nested.mkdir(parents=True)
    assert PackageManager.discover(nested) == tmp_path


@pytest.mark.parametrize(
    "mutate",
    [
        lambda manager: manager.add("requests", language="conda"),
        lambda manager: manager.remove("httpx"),
        lambda manager: manager.upgrade("httpx"),
        lambda manager: manager.upgrade(),
    ],
    ids=["add", "remove", "upgrade-one", "upgrade-all"],
)
def test_manifest_writers_refuse_a_pyproject_source(
    tmp_path: Path, mutate: Callable[[PackageManager], None]
) -> None:
    """`add`/`remove`/`upgrade` refuse to edit an embedded `[tool.chefe]`, pointing at the file."""
    write_pyproject(tmp_path)
    manager = PackageManager(tmp_path)
    with pytest.raises(ChefeError, match="cannot edit the .* manifest inside pyproject.toml"):
        mutate(manager)
