from collections.abc import Callable, Sequence

import pytest

from chefe.backends import PixiGlobal
from chefe.core import ChefeError
from chefe.manager import PackageManager

Workspace = Callable[[str], PackageManager]


def test_global_install_builds_specs(
    workspace: Workspace, recording_backends: Sequence[tuple[str, ...]]
) -> None:
    """The global install turns `[deps]` into conda specs and installs them into a shared env."""
    manager = workspace(
        """
        [deps]
        python = ">=3.11"
        ripgrep = "*"
        """
    )
    manager.glob.install("shared")
    glob = next(c for c in recording_backends if c[1] == "shared")
    specs = glob[2]
    assert "python>=3.11" in specs and "ripgrep" in specs


def test_global_add_remove_and_list_use_workspace_default(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Global mutations default to the workspace name and pass explicit envs through."""
    manager = workspace("[deps]\npython = '*'\n")
    seen: list[tuple[str, str, tuple[str, ...] | str, bool | str]] = []

    monkeypatch.setattr(
        PixiGlobal,
        "add",
        lambda self, name, packages: seen.append(("add", name, packages, "")),
    )
    monkeypatch.setattr(
        PixiGlobal,
        "remove",
        lambda self, name, packages: seen.append(("remove", name, packages, "")),
    )
    monkeypatch.setattr(
        PixiGlobal,
        "show",
        lambda self, name="", regex="", json=False, sort_by="": seen.append(
            ("list", name, regex, json)
        ),
    )

    manager.glob.add("ripgrep")
    manager.glob.remove("ripgrep", env="tools")
    manager.glob.list("rip", env="tools", json=True)

    assert seen == [
        ("add", "w", ("ripgrep",), ""),
        ("remove", "tools", ("ripgrep",), ""),
        ("list", "tools", "rip", True),
    ]


@pytest.mark.parametrize(
    ("call", "match"),
    [
        (lambda manager: manager.glob.add(), "No packages given"),
        (lambda manager: manager.glob.remove(), "No packages given"),
    ],
    ids=["add", "remove"],
)
def test_global_add_remove_require_packages(
    workspace: Workspace, call: Callable[[PackageManager], None], match: str
) -> None:
    """Global add and remove fail clearly when no package names are provided."""
    manager = workspace("[deps]\npython = '*'\n")
    with pytest.raises(ChefeError, match=match):
        call(manager)
