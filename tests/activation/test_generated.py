from collections.abc import Callable
from pathlib import Path

import pytest
from plumbum import local
from pytest_mock import MockerFixture

from chefe.backends import Pixi
from chefe.core import ChefeError
from chefe.manager import PackageManager
from chefe.workspace.generated import GeneratedFiles

Workspace = Callable[[str], PackageManager]


def test_generated_files_replace_complete_content_atomically(tmp_path: Path) -> None:
    """A reader keeps the prior file until the complete replacement is ready."""
    target = tmp_path / "pixi.toml"
    target.write_text("old")
    observed: list[tuple[str, str]] = []
    original = Path.replace

    def inspect(temporary: Path, destination: Path) -> Path:
        observed.append((destination.read_text(), temporary.read_text()))
        return original(temporary, destination)

    with (
        pytest.MonkeyPatch.context() as monkeypatch,
        GeneratedFiles(directory=tmp_path).locked() as files,
    ):
        monkeypatch.setattr(Path, "replace", inspect)
        files.write(target, "complete")

    assert observed == [("old", "complete")]
    assert target.read_text() == "complete" and not list(tmp_path.glob(".pixi.toml.*"))


def test_writer_refuses_to_edit_once_the_sync_lock_is_released(tmp_path: Path) -> None:
    """A writer kept past its `locked()` block refuses to write instead of racing the next sync."""
    with GeneratedFiles(directory=tmp_path).locked() as files:
        assert files.lock.is_locked
    with pytest.raises(ChefeError, match="sync lock"):
        files.write(tmp_path / "pixi.toml", "late")


def test_activate_writes_a_sourceable_script(workspace: Workspace, mocker: MockerFixture) -> None:
    """`chefe activate` writes `.chefe/activate.sh` embedding the pixi hook and pinned modules."""
    manager = workspace('[deps]\npython = "*"\n\n[modules]\nnvidia = "26.3"\ngcc = "15.2.0"\n')
    mocker.patch.object(
        Pixi,
        "shell_hook",
        side_effect=lambda self, env="default": "export PIXI_OK=1",
        autospec=True,
    )
    path = manager.environment.activate()
    script = path.read_text()
    assert path == manager.workspace.out / "activate.sh"
    assert "export PIXI_OK=1" in script
    assert "module load nvidia/26.3 gcc/15.2.0" in script
    assert "command -v module" in script
    assert local["bash"]["-n", str(path)].run(retcode=None)[0] == 0
