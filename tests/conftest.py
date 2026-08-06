import os
import sys
from collections.abc import Iterator, Mapping
from pathlib import Path

# chefe is the one house package never editable-installed, so its own source tree sits off
# `sys.path` and the suite would import the installed wheel. Prepend the in-tree `src`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest
from faker import Faker
from plumbum import local
from pytest_mock import MockerFixture

from chefe.backends import Cargo, Node, Pixi, PixiGlobal, Tool
from chefe.core import Installed
from chefe.manager import PackageManager
from chefe.manifest import Document
from chefe.workspace import DependencyCommands

from .support.workspaces import write_manifest


@pytest.fixture(scope="session")
def faker_instance() -> Faker:
    """A seeded Faker shared across the session so example data stays reproducible."""
    Faker.seed(0xC4EFE)
    return Faker()


@pytest.fixture
def manifest_path(tmp_path: Path) -> Path:
    """A minimal on-disk `chefe.toml` (header only) in a fresh workspace."""
    return write_manifest(tmp_path)


@pytest.fixture
def workspace(tmp_path: Path):
    """A factory: `workspace(body)` writes a `chefe.toml` and returns its `PackageManager`."""

    def make(body: str = "") -> PackageManager:
        write_manifest(tmp_path, body)
        return PackageManager(tmp_path)

    return make


@pytest.fixture
def locked_workspace(tmp_path: Path):
    """A factory: `locked_workspace(text, env)` writes a whole manifest, syncs it, and locks it.

    Returns the manager beside the manifest that sync compiled, which is what a staleness test
    compares the next sync's output against.
    """

    def make(text: str, *, env: str = "default") -> tuple[PackageManager, str]:
        (tmp_path / "chefe.toml").write_text(text)
        manager = PackageManager(tmp_path)
        manager.environment.sync(env)
        manager.pixi.lock.write_text("version: 7\n")
        return manager, manager.pixi.manifest.read_text()

    return make


@pytest.fixture
def pulled(monkeypatch: pytest.MonkeyPatch) -> list[bool]:
    """Record each dependency `pull` instead of mirroring pixi's resolution back."""
    calls: list[bool] = []
    monkeypatch.setattr(DependencyCommands, "pull", lambda self: calls.append(True))
    return calls


@pytest.fixture
def provisioned(monkeypatch: pytest.MonkeyPatch):
    """A factory: `provisioned(conda)` reports ``conda`` as installed, with npm and cargo empty."""

    def make(conda: Mapping[str, Installed]) -> None:
        monkeypatch.setattr(Pixi, "installed", lambda self, env: dict(conda))
        monkeypatch.setattr(Node, "installed", lambda self, env: {})
        monkeypatch.setattr(Cargo, "installed", lambda self, env: {})

    return make


@pytest.fixture
def document(manifest_path: Path) -> Document:
    """A `Document` over a fresh header-only manifest."""
    return Document(manifest_path)


@pytest.fixture(autouse=True)
def stable_chefe_version(mocker: MockerFixture) -> None:
    """Keep source-tree tests independent of installed package metadata."""
    mocker.patch("chefe.manifest.schema.root.manifest.version", return_value="0.0.test")


@pytest.fixture
def tool_paths(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, str]]:
    """Stub `pixi`/`npm`/`cargo` executables on plumbum's PATH.

    Backend commands resolve without the real tools installed, and `pytest-subprocess`
    intercepts the actual invocation. Yields each tool's resolved absolute path, which is what
    plumbum runs and therefore what a fake registers.
    """
    bindir = tmp_path_factory.mktemp("bin")
    paths: dict[str, str] = {}
    for tool in ("pixi", "npm", "cargo", "pnpm", "yarn", "aube"):
        executable = bindir / tool
        executable.write_text("#!/bin/sh\n")
        executable.chmod(0o755)
        paths[tool] = str(executable)
    with local.env(PATH=f"{bindir}{os.pathsep}{local.env['PATH']}"):
        yield paths


@pytest.fixture(autouse=True)
def isolated_pixi_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Keep every test's global pixi home inside its own `tmp_path`, never the real `~/.pixi`."""
    home = tmp_path / "pixi"
    monkeypatch.setenv("PIXI_HOME", str(home))
    return home


@pytest.fixture
def pixi(tmp_path: Path) -> Pixi:
    """A Pixi backend pinned to a fresh workspace's generated env dir."""
    return Pixi(tmp_path)


@pytest.fixture
def cargo(tmp_path: Path, pixi: Pixi) -> Cargo:
    """A Cargo backend installing into the same workspace's pixi env."""
    return Cargo(tmp_path, pixi)


@pytest.fixture
def pixi_calls(mocker: MockerFixture) -> list[tuple[str, ...]]:
    """Record every `Pixi.__call__` as `(verb, *flags, *args)` instead of running pixi."""
    calls: list[tuple[str, ...]] = []
    mocker.patch.object(
        Pixi,
        "__call__",
        side_effect=lambda self, verb, *args, **flags: calls.append(
            (verb, *Tool.flags(**flags), *args)
        ),
        autospec=True,
    )
    return calls


@pytest.fixture
def recording_backends(mocker: MockerFixture) -> list[tuple[str, ...]]:
    """Replace every subprocess seam with a recorder of `(Backend, verb, *flags, *args)`.

    Returns the shared call list so a test can assert exactly which argv the manager built,
    while the real tools are never invoked. Every backend's `__call__` and pixi's exit-code
    sibling share one recorder, so the list is a single cross-backend, ordered, flag-normalized
    view of every invocation. `Node` is the base for every JS driver (npm/pnpm/yarn/aube), so
    patching it once records whichever one a manifest selects, under its own class name.
    """
    calls: list[tuple[str, ...]] = []

    def record(self: Tool, verb: str, *args: str, **flags: bool | str | None) -> bool:
        calls.append((type(self).__name__, verb, *Tool.flags(**flags), *args))
        return True

    def record_code(self: Tool, verb: str, *args: str, **flags: bool | str | None) -> int:
        record(self, verb, *args, **flags)
        return 0

    def record_launch(self: Pixi, verb: str, *args: str, env: str, resolve: bool = False) -> int:
        calls.append((type(self).__name__, verb, *(("--resolve",) if resolve else ()), env, *args))
        return 0

    def record_install(self: Pixi, env: str, *, resolve: bool = False) -> None:
        calls.append(
            (type(self).__name__, "install", *(("--resolve",) if resolve else ()), "-e", env)
        )

    def record_enter(self: Pixi, env: str, *, resolve: bool = False) -> int:
        calls.append(
            (type(self).__name__, "shell", *(("--resolve",) if resolve else ()), "-e", env)
        )
        return 0

    seams = [
        (Pixi, "exit_code", record_code),
        (Pixi, "launch", record_launch),
        (Pixi, "enter", record_enter),
        (Pixi, "install", record_install),
        (PixiGlobal, "install", record),
        # `install` ends by regenerating `activate.sh`; stub the pixi shell-hook seam so a
        # backend-only test never shells out to a real pixi.
        (Pixi, "shell_hook", lambda self, env="default": ""),
        (Cargo, "sync", lambda self, env, declared: calls.append(("Cargo", "sync"))),
    ]
    for backend in (Pixi, Node, Cargo):
        mocker.patch.object(backend, "__call__", side_effect=record, autospec=True)
        mocker.patch.object(backend, "installed", side_effect=lambda self, env: {}, autospec=True)
    for owner, seam, recorder in seams:
        mocker.patch.object(owner, seam, side_effect=recorder, autospec=True)
    return calls
