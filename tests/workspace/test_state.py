from pathlib import Path

from chefe.workspace.state import SyncState


def test_state_round_trips_through_its_own_render(tmp_path: Path) -> None:
    state = SyncState(
        envs={"default": "abc123", "gpu": "def456"},
        resolution_inputs="feed99",
        resolution_stale=True,
    )
    SyncState.path(tmp_path).write_text(state.render(), encoding="utf-8")
    loaded = SyncState.load(tmp_path)
    assert loaded == state


def test_missing_state_with_no_markers_is_empty_and_reads_stale(tmp_path: Path) -> None:
    loaded = SyncState.load(tmp_path)
    assert loaded.envs == {} and not loaded.resolution_stale
    assert loaded.envs.get("default") != "anything"


def test_corrupt_state_reads_as_empty(tmp_path: Path) -> None:
    SyncState.path(tmp_path).write_text("not [ toml", encoding="utf-8")
    assert SyncState.load(tmp_path) == SyncState()
