from collections.abc import Callable, Sequence
from pathlib import Path

import pytest
from plumbum import local

from chefe.backends import Pixi, PixiEngine
from chefe.core import ChefeError
from chefe.manager import PackageManager
from chefe.workspace import DependencyCommands

from ..support.workspaces import executable

Workspace = Callable[[str], PackageManager]


def test_node_backend_uses_the_named_manager(workspace: Workspace) -> None:
    """`Workspace.node` builds a `Node` carrying the manifest's `[nodejs] manager` name.

    The `Node` is rooted in the env dir, and the per-manager genericity itself lives in
    `test_backends`.
    """
    manager = workspace(
        """
        [deps]
        nodejs = "*"

        [nodejs]
        manager = "pnpm"

        [nodejs.deps]
        x = "*"
        """
    )
    node = manager.execution.runtime.node("default")
    assert node.name == "pnpm"
    assert node.cwd() == manager.workspace.out


def test_update_and_upgrade_and_shell_and_run(
    workspace: Workspace,
    recording_backends: Sequence[tuple[str, ...]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The remaining pixi-driven verbs each reach the backend with their verb."""
    monkeypatch.setattr(DependencyCommands, "pull", lambda self: None)
    manager = workspace(
        """
        [deps]
        python = "*"

        [tasks]
        build = "echo build"
        """
    )
    manager.environment.update()
    manager.dependencies.upgrade("python")
    manager.execution.shell()
    manager.execution.run("build", "--flag")
    assert {"update", "upgrade", "shell", "run"} <= {c[1] for c in recording_backends}


@pytest.mark.parametrize("code", [0, 3, 5])
@pytest.mark.parametrize("verb", ["run", "shell"])
def test_passthrough_verbs_exit_with_the_inner_code(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch, verb: str, code: int
) -> None:
    """`run` and `shell` both propagate the inner command's exit status.

    The pixi exit-code seam raises `SystemExit(code)` on failure and stays silent on success.
    """
    manager = workspace(
        """
        [deps]
        python = '*'

        [tasks]
        build = "echo build"
        """
    )
    monkeypatch.setattr(Pixi, "launch", lambda self, *a, **k: code)
    monkeypatch.setattr(Pixi, "enter", lambda self, *a, **k: code)
    invoke = (lambda: manager.execution.run("build")) if verb == "run" else manager.execution.shell
    if code:
        with pytest.raises(SystemExit) as exit_info:
            invoke()
        assert exit_info.value.code == code
    else:
        assert invoke() is None


def test_run_and_shell_expose_npm_bins(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """npm dev CLIs are runnable without defining one task per executable."""
    manager = workspace(
        """
        [deps]
        nodejs = "*"

        [nodejs.dev.deps]
        "@tobilu/qmd" = ">=0.1"
        """
    )
    manager.environment.sync()
    binary = executable(manager.execution.runtime.node("default").binary_dir(), "qmd")
    seen: list[tuple[str, bool]] = []

    def note(verb: str) -> None:
        seen.append((verb, str(binary.parent) in local.env["PATH"]))

    monkeypatch.setattr(Pixi, "launch", lambda self, verb, *a, **k: note(verb) or 0)
    monkeypatch.setattr(Pixi, "enter", lambda self, *a, **k: note("shell") or 0)
    manager.execution.run("qmd", "--version")
    manager.execution.shell()
    assert seen == [("run", True), ("shell", True)]


def test_run_missing_name_reports_task_or_executable(workspace: Workspace) -> None:
    """A missing `chefe run` target explains that the name can be a task or an executable."""
    manager = workspace("[deps]\npython = '*'\n")
    with pytest.raises(ChefeError, match="No task or executable named `missing-chefe-tool`"):
        manager.execution.run("missing-chefe-tool")


def test_run_leading_env_flag_selects_a_declared_environment(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`chefe run --env <name> <cmd>` runs `<cmd>` in the named `[envs.*]` env.

    The env threads through pixi as `run -e <name>`, with the flag stripped from the command.
    """
    manager = workspace(
        """
        [deps]
        python = "*"

        [envs.gpu]
        no-default = true

        [envs.gpu.deps]
        python = "*"

        [envs.gpu.tasks]
        build = "echo build"
        """
    )
    seen: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        Pixi, "launch", lambda self, verb, *a, env, **k: seen.append((verb, env, *a)) or 0
    )
    manager.execution.run("--env", "gpu", "build", "--flag")
    assert seen == [("run", "gpu", "build", "--flag")]


def test_run_unknown_env_fails_fast(workspace: Workspace) -> None:
    """An `--env` that names no declared `[envs.*]` table is rejected before reaching pixi."""
    manager = workspace("[deps]\npython = '*'\n")
    with pytest.raises(ChefeError, match="No environment `ghost` is declared"):
        manager.execution.run("--env", "ghost", "python")


@pytest.mark.parametrize(
    "argv",
    [(), ("--env", "gpu")],
    ids=["missing-command", "environment-without-command"],
)
def test_run_requires_a_command_after_optional_environment(
    workspace: Workspace, argv: tuple[str, ...]
) -> None:
    """A missing executable fails before activation with one concise user error."""
    manager = workspace("[deps]\npython = '*'\n")
    with pytest.raises(ChefeError, match="needs"):
        manager.execution.run(*argv)


def test_x_exits_with_the_inner_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`chefe x` preserves a failing ephemeral command's exit status."""
    monkeypatch.setattr(PixiEngine, "exec", lambda self, specs, args: 13)
    with pytest.raises(SystemExit) as exit_info:
        PackageManager(root=tmp_path).execution.x("ruff")
    assert exit_info.value.code == 13


def test_x_runs_ephemeral(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """x runs a throwaway command through the pixi exec seam, with no manifest needed."""
    seen: list[tuple[tuple[str, ...], tuple[str, ...]]] = []
    monkeypatch.setattr(
        PixiEngine, "exec", lambda self, specs, args: bool(seen.append((specs, args)))
    )
    PackageManager(root=tmp_path).execution.x("ruff", "check", ".", with_=("ruff",))
    assert seen == [(("ruff",), ("ruff", "check", "."))]
