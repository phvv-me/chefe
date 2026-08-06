import json
from collections.abc import Mapping
from pathlib import Path

import pytest
from pytest_subprocess import FakeProcess

from chefe.backends import Node


def test_node_available_requires_package_json(tmp_path: Path) -> None:
    """The JS backend refuses to run until a `package.json` exists in the env dir."""
    node = Node(tmp_path)
    assert node.available() is False
    (tmp_path / "package.json").write_text("{}")
    assert node.available() is True


def test_node_installed_reads_node_modules(tmp_path: Path) -> None:
    """`installed` discovers both plain and scoped packages under node_modules."""
    for rel, name, version in (
        ("node_modules/prettier", "prettier", "3.2.0"),
        ("node_modules/@scope/pkg", "@scope/pkg", "1.0.0"),
    ):
        directory = tmp_path / rel
        directory.mkdir(parents=True)
        (directory / "package.json").write_text(json.dumps({"name": name, "version": version}))
    found = Node(tmp_path).installed("default")
    assert found["prettier"].version == "3.2.0"
    assert found["@scope/pkg"].kind == "npm"


@pytest.mark.parametrize("manager", ["npm", "pnpm", "yarn", "aube"])
def test_node_runs_the_named_manager_in_the_env_dir(
    manager: str, fp: FakeProcess, tmp_path: Path, tool_paths: Mapping[str, str]
) -> None:
    """The JS backend invokes whatever manager it is named, targeting the env dir by cwd.

    The same call shape works for every tool, so a new package manager needs no code, only a name.
    """
    (tmp_path / "package.json").write_text("{}")
    node = Node(tmp_path, manager)
    assert node.name == manager and node.cwd() == tmp_path
    fp.register([tool_paths[manager], fp.any()], stdout="")
    node("install")
    assert list(fp.calls[-1]) == [tool_paths[manager], "install"]
