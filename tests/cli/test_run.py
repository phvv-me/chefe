from pathlib import Path

import pytest

from chefe.backends import Pixi
from chefe.cli import build
from chefe.manager import PackageManager

from ..support.workspaces import write_manifest


def run_workspace(root: Path, body: str = '[tasks]\nbuild = "echo build"\n') -> None:
    """Drop a manifest declaring the `build` task the `run` passthrough tests invoke."""
    write_manifest(root, body)


def recording_exit_code(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, ...]]:
    """Stub Pixi's locked environment seam with a success recorder and return its calls."""
    seen: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        Pixi,
        "launch",
        lambda self, verb, *args, env, resolve=False, **flags: (
            seen.append((verb, env, *args, *(("--resolve",) if resolve else ()))) or 0
        ),
    )
    return seen


def test_run_passes_help_flags_through_to_the_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`chefe run build --help` reaches the target verbatim instead of printing chefe's usage.

    This is the help passthrough bug: cyclopts intercepts its help flags anywhere in a
    command's tokens, so `chefe run atpx --help` printed chefe run's own page and the flag
    never reached atpx. `run` now registers without help flags and forwards them like any
    other leading-hyphen passthrough flag.
    """
    run_workspace(tmp_path)
    seen = recording_exit_code(monkeypatch)
    app = build(PackageManager(root=tmp_path))
    with pytest.raises(SystemExit) as exit_info:
        app(["run", "build", "--help"])
    assert exit_info.value.code in (0, None)
    assert seen == [("run", "default", "build", "--help")]


def test_run_resolve_flag_is_consumed_before_the_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`chefe run --resolve` permits solving without forwarding the flag to the task."""
    run_workspace(tmp_path)
    seen = recording_exit_code(monkeypatch)
    app = build(PackageManager(root=tmp_path))

    with pytest.raises(SystemExit) as exit_info:
        app(["run", "--resolve", "build"])

    assert exit_info.value.code in (0, None)
    assert seen == [("run", "default", "build", "--resolve")]


@pytest.mark.parametrize("argv", [("--help",), ("-h",), ("--resolve", "--help")])
def test_run_without_a_target_still_prints_its_own_help(
    argv: tuple[str, ...], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A help flag with no task name keeps printing the run command's own page."""
    run_workspace(tmp_path)
    app = build(PackageManager(root=tmp_path))
    with pytest.raises(SystemExit) as exit_info:
        app(["run", *argv])
    assert exit_info.value.code in (0, None)
    out = capsys.readouterr().out
    assert "chefe run" in out
    assert "task or installed executable" in out


def test_root_help_is_untouched(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """`chefe --help` still prints the app's own page listing the commands."""
    run_workspace(tmp_path)
    app = build(PackageManager(root=tmp_path))
    with pytest.raises(SystemExit) as exit_info:
        app(["--help"])
    assert exit_info.value.code in (0, None)
    out = capsys.readouterr().out
    assert "One manifest, many package managers." in out
    assert "run" in out and "install" in out


def test_run_env_flag_and_help_flag_both_reach_the_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`chefe run -e gpu build --help` selects the env and forwards the flag to the task."""
    run_workspace(
        tmp_path,
        """
            [envs.gpu]
            no-default = true

            [envs.gpu.deps]
            python = "*"

            [envs.gpu.tasks]
            build = "echo build"
        """,
    )
    seen = recording_exit_code(monkeypatch)
    app = build(PackageManager(root=tmp_path))
    with pytest.raises(SystemExit) as exit_info:
        app(["run", "-e", "gpu", "build", "--help"])
    assert exit_info.value.code in (0, None)
    assert seen == [("run", "gpu", "build", "--help")]
