from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from faker import Faker
from plumbum import local
from pytest_mock import MockerFixture

from chefe.backends import Cargo, Node, Pixi, Tool
from chefe.manager import PackageManager
from chefe.manifest import Document

# A `[workspace]` header pinned to a fixed platform so generated manifests are deterministic.
HEADER = '[workspace]\nname = "w"\nplatforms = ["linux-64"]\n\n'


@pytest.fixture(scope="session")
def faker_instance() -> Faker:
    """A seeded Faker shared across the session so example data stays reproducible."""
    Faker.seed(0xC4EFE)
    return Faker()


def write_manifest(root: Path, body: str = "") -> Path:
    """Drop a `chefe.toml` (header prepended) under ``root`` and return its path."""
    path = root / "chefe.toml"
    path.write_text(HEADER + body)
    return path


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
def document(manifest_path: Path) -> Document:
    """A `Document` over a fresh header-only manifest."""
    return Document(manifest_path)


@pytest.fixture
def tool_paths(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, str]]:
    """Stub `pixi`/`npm`/`cargo` executables on plumbum's PATH so backend commands resolve
    without the real tools installed; `pytest-subprocess` intercepts the actual invocation.
    Yields each tool's resolved absolute path (what plumbum runs, so what a fake registers).
    """
    bindir = tmp_path_factory.mktemp("bin")
    paths: dict[str, str] = {}
    for tool in ("pixi", "npm", "cargo", "pnpm", "bun", "aube"):
        executable = bindir / tool
        executable.write_text("#!/bin/sh\n")
        executable.chmod(0o755)
        paths[tool] = str(executable)
    with local.env(PATH=f"{bindir}{os.pathsep}{local.env['PATH']}"):
        yield paths


@pytest.fixture
def recording_backends(mocker: MockerFixture) -> list[tuple[str, ...]]:
    """Replace every subprocess seam with a recorder of `(Backend, verb, *flags, *args)`.

    Returns the shared call list so a test can assert exactly which argv the manager built,
    while the real tools are never invoked. Every backend's `__call__` shares one recorder,
    so the list is a single cross-backend, ordered, flag-normalized view of every invocation.
    """
    calls: list[tuple[str, ...]] = []

    def record(self: object, verb: str, *args: str, **flags: bool | str | None) -> bool:
        calls.append((type(self).__name__, verb, *Tool.flags(**flags), *args))
        return True

    # `Node` is the base for every JS driver (npm/pnpm/bun/aube), so patching it once records
    # whichever one a manifest selects, under its own class name.
    for backend in (Pixi, Node, Cargo):
        mocker.patch.object(backend, "__call__", side_effect=record, autospec=True)
        mocker.patch.object(backend, "installed", side_effect=lambda self, env: {}, autospec=True)
    mocker.patch.object(
        Cargo,
        "sync",
        side_effect=lambda self, env, declared: calls.append(("Cargo", "sync")),
        autospec=True,
    )
    mocker.patch.object(Pixi, "global_install", side_effect=record, autospec=True)
    return calls
