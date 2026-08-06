from collections.abc import Callable, Mapping

import pytest

from chefe.backends import Cargo, Node, Pixi
from chefe.core import Installed
from chefe.manager import PackageManager
from chefe.report import TreeReport

Workspace = Callable[[str], PackageManager]
Provisioned = Callable[[Mapping[str, Installed]], None]


def test_tree_renders_against_installed(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """tree reconciles declared vs installed across sources without raising."""
    monkeypatch.setattr(
        Pixi,
        "installed",
        lambda self, env: {
            "python": Installed(version="3.12.0", kind="conda", explicit=True),
            "numpy": Installed(version="2.0.0", kind="conda", explicit=False),
        },
    )
    monkeypatch.setattr(Node, "installed", lambda self, env: {})
    monkeypatch.setattr(Cargo, "installed", lambda self, env: {})
    manager = workspace(
        """
        [deps]
        python = ">=3.11"
        ripgrep = "*"
        """
    )
    manager.dependencies.tree("default")


def test_tree_renders_a_null_version_path_dep_without_crashing(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An editable/path dep pixi lists with a null version renders as `(path)`, not a crash.

    pixi reports a local path/editable checkout (the house packages installed `editable = true`)
    with `version = null`, which used to fail `Installed` validation and take down `chefe tree`.
    The declared dep still reads as installed, shown as `(path)`.
    """
    monkeypatch.setattr(
        Pixi,
        "installed",
        lambda self, env: {
            "python": Installed(version="3.12.0", kind="conda", explicit=True),
            "lote": Installed(version=None, kind="pypi", explicit=True),
        },
    )
    monkeypatch.setattr(Node, "installed", lambda self, env: {})
    monkeypatch.setattr(Cargo, "installed", lambda self, env: {})
    manager = workspace(
        """
        [deps]
        python = ">=3.11"

        [python.deps]
        lote = "*"
        """
    )
    manager.dependencies.tree("default")
    assert "(path)" in capsys.readouterr().out


def test_tree_normalizes_python_names_and_accepts_conda_resolution(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Python declarations match PEP 503 names and packages Pixi resolved from conda."""
    monkeypatch.setattr(
        Pixi,
        "installed",
        lambda self, env: {
            "types_networkx": Installed(version="3.6.1", kind="pypi", explicit=True),
            "httpx": Installed(version="0.28.1", kind="conda", explicit=True),
        },
    )
    monkeypatch.setattr(Node, "installed", lambda self, env: {})
    monkeypatch.setattr(Cargo, "installed", lambda self, env: {})
    manager = workspace(
        """
        [deps]
        python = "*"

        [python.deps]
        types-networkx = ">=3.6"
        httpx = ">=0.28"
        """
    )

    installed = manager.environment.runtime.installed_by_source("default")

    assert installed["python"] == {"types-networkx": "3.6.1", "httpx": "0.28.1"}


@pytest.mark.parametrize(
    ("spec", "version", "bucket"),
    [(">=1.0", None, "missing"), (">=1.0", "1.5", "ok"), (">=2.0", "1.5", "drift")],
)
def test_row_status_buckets(spec: str, version: str | None, bucket: str) -> None:
    """row_status maps a declared-vs-installed pair to the right tally bucket."""
    assert TreeReport.row_status(spec, version)[2] == bucket


def test_tree_plan_reports_install_update_and_remove(
    workspace: Workspace, provisioned: Provisioned, capsys: pytest.CaptureFixture[str]
) -> None:
    """`chefe tree --plan` is a dry run: it names what an install would add, update, and remove.

    This advances the roadmap's `chefe tree` dry run. A declared-but-absent dep is an install, a
    drifted one an update, and an explicit installed dep no longer declared a removal, while a
    transitive (non-explicit) dep is left to the solver and never shows up as a removal.
    """
    provisioned(
        {
            "python": Installed(version="3.12.0", kind="conda", explicit=True),
            "ripgrep": Installed(version="13.0.0", kind="conda", explicit=True),
            "stale": Installed(version="1.0.0", kind="conda", explicit=True),
            "libfoo": Installed(version="9.9", kind="conda", explicit=False),
        }
    )
    manager = workspace(
        """
        [deps]
        python = ">=3.11"
        ripgrep = ">=14"
        numpy = ">=2"
        """
    )
    manager.dependencies.tree("default", plan=True)
    out = capsys.readouterr().out
    assert "install would change" in out
    assert "install" in out and "numpy >=2" in out
    assert "update" in out and "ripgrep 13.0.0 → >=14" in out
    assert "remove" in out and "stale" in out
    assert "libfoo" not in out  # transitive deps are the solver's, never planned for removal


def test_tree_plan_reports_up_to_date_when_matched(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `--plan` over a fully provisioned env reports no changes rather than an empty list."""
    monkeypatch.setattr(
        Pixi,
        "installed",
        lambda self, env: {"python": Installed(version="3.12.0", kind="conda", explicit=True)},
    )
    monkeypatch.setattr(Node, "installed", lambda self, env: {})
    monkeypatch.setattr(Cargo, "installed", lambda self, env: {})
    manager = workspace('[deps]\npython = ">=3.11"\n')
    manager.dependencies.tree("default", plan=True)
    assert "up to date" in capsys.readouterr().out
