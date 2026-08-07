import json
from collections.abc import Callable, Mapping
from pathlib import Path

import pytest
from cyclopts import App
from pytest_subprocess import FakeProcess

from chefe.cli import build
from chefe.manager import PackageManager

from ..support.workspaces import conda_workspace

# cargo has no global install of its own, so the env prefix has to be handed to it as
# `--root`, which is why the two argvs cannot share a shape.
_GLOBAL_ADD_ARGV = {
    "npm": ["install", "-g", "typescript"],
    "cargo": ["install", "--root", "{prefix}", "typescript"],
}


def succeeds(app: App, argv: list[str]) -> None:
    """Run ``argv`` through ``app`` and assert the CLI ended successfully."""
    # cyclopts always raises SystemExit on a run, success or failure, so success can only be
    # told apart from failure by inspecting the exit code it carries.
    with pytest.raises(SystemExit) as exit_info:
        app(argv)
    assert exit_info.value.code in (0, None)


def existing_global_env(fp: FakeProcess, pixi: str, *, name: str) -> None:
    """Register `pixi global list --json` so the manager sees env ``name`` as already present."""
    fp.register([pixi, "global", "list", "--json"], stdout=json.dumps([{"name": name}]))


def empty_global_env(fp: FakeProcess, pixi: str) -> None:
    """Register `pixi global list --json` as empty, so the manager treats every env as missing."""
    fp.register([pixi, "global", "list", "--json"], stdout=json.dumps([]))


@pytest.mark.parametrize(
    ("language", "tool"),
    [("nodejs", "npm"), ("npm", "npm"), ("rust", "cargo"), ("cargo", "cargo")],
    ids=["nodejs", "npm-alias", "rust", "cargo-alias"],
)
def test_global_add_language_routes_to_the_right_backend(
    *,
    language: str,
    tool: str,
    fp: FakeProcess,
    tool_paths: Mapping[str, str],
    tmp_path: Path,
) -> None:
    """`chefe global add <pkg> -l <lang>` reaches the env's own pip/npm/cargo, never `pixi global`.

    This is bug 1: `global add` had no `-l`, so `-l nodejs` was swallowed as a package and handed
    to `pixi global add`, which rejected the leading hyphen. Each language must build the exact
    backend argv against the global env prefix instead.
    """
    conda_workspace(tmp_path)
    prefix = tmp_path / "pixi" / "envs" / "life"
    binary = str(prefix / "bin" / tool)
    existing_global_env(fp, tool_paths["pixi"], name="life")
    fp.register([binary, fp.any()], stdout="")
    app = build(PackageManager(root=tmp_path))
    with pytest.raises(SystemExit) as exit_info:
        app(["global", "add", "typescript", "-l", language])
    assert exit_info.value.code in (0, None)
    assert list(fp.calls[-1]) == [
        binary,
        *(part.replace("{prefix}", str(prefix)) for part in _GLOBAL_ADD_ARGV[tool]),
    ]


def test_global_add_pypi_routes_to_env_pip(
    fp: FakeProcess, tool_paths: Mapping[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`-l python`/`-l pypi` installs through the global env's own python `-m pip`."""
    monkeypatch.setenv("PIXI_HOME", str(tmp_path / "pixi"))
    conda_workspace(tmp_path)
    python = str(tmp_path / "pixi" / "envs" / "life" / "bin" / "python")
    existing_global_env(fp, tool_paths["pixi"], name="life")
    fp.register([python, fp.any()], stdout="")
    app = build(PackageManager(root=tmp_path))
    with pytest.raises(SystemExit) as exit_info:
        app(["global", "add", "ruff", "-l", "python"])
    assert exit_info.value.code in (0, None)
    assert list(fp.calls[-1]) == [python, "-m", "pip", "install", "ruff"]


@pytest.mark.parametrize(
    ("register", "verb"),
    [
        (lambda fp, pixi: existing_global_env(fp, pixi, name="life"), "add"),
        (empty_global_env, "install"),
    ],
    ids=["existing-env", "missing-env"],
)
def test_global_add_conda_targets_the_workspace_env_with_the_verb_its_state_allows(
    *,
    register: Callable[[FakeProcess, str], None],
    verb: str,
    fp: FakeProcess,
    tool_paths: Mapping[str, str],
    tmp_path: Path,
) -> None:
    """With no `-e`, a conda `global add` targets `workspace.name` (here `life`).

    `pixi global add` needs an existing env, so a missing one is created with the `install` verb
    instead. That was bug 2: `global add` hard-errored with "Environment life doesn't exist"
    because it always used `add`.
    """
    conda_workspace(tmp_path)
    register(fp, tool_paths["pixi"])
    fp.register([tool_paths["pixi"], fp.any()], stdout="")
    succeeds(build(PackageManager(root=tmp_path)), ["global", "add", "ripgrep"])
    assert list(fp.calls[-1]) == [
        tool_paths["pixi"],
        "global",
        verb,
        "--environment",
        "life",
        "ripgrep",
    ]


def test_global_add_multiple_packages_in_one_call(
    fp: FakeProcess, tool_paths: Mapping[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Several packages ride one `global add` invocation into a single pixi call."""
    monkeypatch.setenv("PIXI_HOME", str(tmp_path / "pixi"))
    conda_workspace(tmp_path)
    existing_global_env(fp, tool_paths["pixi"], name="life")
    fp.register([tool_paths["pixi"], fp.any()], stdout="")
    app = build(PackageManager(root=tmp_path))
    with pytest.raises(SystemExit):
        app(["global", "add", "ripgrep", "fd-find", "bat"])
    assert list(fp.calls[-1])[-3:] == ["ripgrep", "fd-find", "bat"]


def test_global_add_unknown_language_is_a_clean_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An unsupported `-l` value fails with a listing of valid languages, not a pixi crash."""
    conda_workspace(tmp_path)
    app = build(PackageManager(root=tmp_path))
    with pytest.raises(SystemExit) as exit_info:
        app(["global", "add", "ripgrep", "-l", "haskell"])
    assert exit_info.value.code == 1
    assert "Unknown language `haskell`" in capsys.readouterr().err


def test_global_add_runtime_language_provisions_missing_env(
    fp: FakeProcess, tool_paths: Mapping[str, str], tmp_path: Path
) -> None:
    """A `-l nodejs` add against a missing env provisions the nodejs runtime, then runs npm.

    This was the last `global add` friction: a runtime add hard-stopped on a fresh env with a
    pointer to `chefe global install`. Now the env is created with its runtime on demand, so
    `chefe global add codex -l nodejs` is a single command, the conda `install`-verb create path
    extended to the runtime languages.
    """
    conda_workspace(tmp_path)
    npm = str(tmp_path / "pixi" / "envs" / "life" / "bin" / "npm")
    empty_global_env(fp, tool_paths["pixi"])
    fp.register([tool_paths["pixi"], fp.any()], stdout="")
    fp.register([npm, fp.any()], stdout="")
    succeeds(build(PackageManager(root=tmp_path)), ["global", "add", "typescript", "-l", "nodejs"])

    calls = [list(call) for call in fp.calls]
    assert [tool_paths["pixi"], "global", "install", "--environment", "life", "nodejs"] in calls
    assert calls[-1] == [npm, "install", "-g", "typescript"]


def test_global_add_without_packages_is_a_clean_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`chefe global add` with no package names fails with usage, not an empty pixi call."""
    conda_workspace(tmp_path)
    app = build(PackageManager(root=tmp_path))
    with pytest.raises(SystemExit) as exit_info:
        app(["global", "add"])
    assert exit_info.value.code == 1
    assert "No packages given" in capsys.readouterr().err
