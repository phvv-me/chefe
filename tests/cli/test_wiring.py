import functools
import runpy
import warnings
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest
from cyclopts import App

from chefe.cli import build, detect_shell
from chefe.manager import PackageManager
from chefe.shared import GlobalEnv
from chefe.workspace import (
    DependencyCommands,
    EnvironmentCommands,
    ExecutionCommands,
    Workspace,
)

from ..support.workspaces import conda_workspace, write_manifest

CommandArgument = str | bool | tuple[str, ...] | None
Recorder = Callable[..., None]
CommandGroup = DependencyCommands | EnvironmentCommands | ExecutionCommands | GlobalEnv


# cli.py must stay pure wiring, so a newly registered command belongs here the same day.
_COMMANDS = [
    (["init", "proj"], "environment.init"),
    (["sync"], "environment.sync"),
    (["install", "serving"], "environment.install"),
    (["activate"], "environment.activate"),
    (["update"], "environment.update"),
    (["clean"], "environment.clean"),
    (["run", "build", "--", "-x"], "execution.run"),
    (["x", "ruff", "check", "."], "execution.x"),
    (["exec", "ruff", "check", "."], "execution.x"),
    (["shell"], "execution.shell"),
    (["tree"], "dependencies.tree"),
    (["add", "numpy", "-l", "python"], "dependencies.add"),
    (["upgrade", "numpy"], "dependencies.upgrade"),
    (["remove", "numpy"], "dependencies.remove"),
    (["global", "install", "shared"], "glob.install"),
]


def recording_manager(seen: list[str]) -> PackageManager:
    """A manager whose every command records its name instead of doing work.

    Each override keeps the real method's signature (via ``functools.wraps``) so cyclopts
    still parses each command exactly as in production. Every label is dotted, because the CLI
    registers bound methods off the command group that owns them rather than off the manager.
    """
    manager = PackageManager()

    def spy(target: CommandGroup, name: str, *, label: str) -> Recorder:
        @functools.wraps(getattr(target, name))
        def record(*args: CommandArgument, **kwargs: CommandArgument) -> None:
            seen.append(label)

        return record

    for _, label in _COMMANDS:
        owner, _, attr = label.rpartition(".")
        target = getattr(manager, owner) if owner else manager
        setattr(target, attr, spy(target, attr, label=label))
    return manager


@pytest.mark.parametrize(
    ("argv", "method"), _COMMANDS, ids=[f"{c[0][0]}/{c[1]}" for c in _COMMANDS]
)
def test_cli_delegates_to_manager(argv: list[str], method: str) -> None:
    """Every command parses and forwards exactly once to its manager method."""
    seen: list[str] = []
    app = build(recording_manager(seen))
    with pytest.raises(SystemExit) as exit_info:
        app(argv)
    assert exit_info.value.code in (0, None)
    assert seen == [method]


def test_cli_prints_chefe_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """User mistakes are shown as concise CLI errors, not Python tracebacks."""
    write_manifest(
        tmp_path,
        """
        [deps]
        python = "*"
        """,
    )
    app = build(PackageManager(root=tmp_path))
    with pytest.raises(SystemExit) as exit_info:
        app(["add", "ripgrep", "-l", "rust"])
    assert exit_info.value.code == 1
    assert "Language `rust` is not declared in [deps]" in capsys.readouterr().err


# Every entry must fail before any backend process starts, which is why no case here
# registers a fake process.
_FAILURES: list[tuple[str | None, list[str], str]] = [
    ('[deps]\npython = "*"\n', ["install"], "pixi.lock is missing"),
    ('[tasks]\nbuild = "echo build"\n', ["run", "build"], "pixi.lock is missing"),
    ('[deps]\npython = "*"\n', ["shell"], "pixi.lock is missing"),
    ('[tasks]\nbuild = "echo build"\n', ["run", "-e", "gpu", "build"], "No environment `gpu`"),
    ('[deps]\npython = "*"\n', ["add"], "No packages given"),
    ('[deps]\npython = "*"\n', ["global", "add", "rg", "-l", "haskell"], "Unknown language"),
    (None, ["install"], "chefe.toml not found"),
    ("[deps\n", ["sync"], "invalid TOML"),
]


@pytest.mark.parametrize(
    ("body", "argv", "message"),
    _FAILURES,
    ids=[f"{argv[0]}-{message.split()[0].strip('`')}" for _, argv, message in _FAILURES],
)
def test_failing_commands_exit_non_zero_with_the_error_on_stderr(
    body: str | None,
    argv: list[str],
    message: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A command that reports a failure stops the process and says so on the failure channel.

    Both halves are the contract a scripted caller leans on. `chefe install` refusing to
    provision must not read as a green step to anything checking the exit status, and the reason
    must not land in the stdout a CI job or an agent captures as the command's own output, where
    a redirect hides it and a reader mistakes it for a finished run.
    """
    if body is not None:
        write_manifest(tmp_path, body)
    app = build(PackageManager(root=tmp_path))

    with pytest.raises(SystemExit) as exit_info:
        app(argv)

    captured = capsys.readouterr()
    assert exit_info.value.code == 1
    # rich wraps a long message to the console width, so compare against the unwrapped text.
    assert message in captured.err.replace("\n", " ")
    assert message not in captured.out.replace("\n", " ")


def test_install_that_provisions_exits_zero_with_a_clean_failure_channel(
    tmp_path: Path,
    recording_backends: Sequence[tuple[str, ...]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The succeeding half of the same contract: a real install ends green and says nothing."""
    write_manifest(tmp_path, '[deps]\npython = "*"\n')
    app = build(PackageManager(root=tmp_path))

    with pytest.raises(SystemExit) as exit_info:
        app(["install"])

    assert exit_info.value.code in (0, None)
    assert capsys.readouterr().err == ""
    assert ("Pixi", "install", "-e", "default") in recording_backends


def test_module_entrypoint_invokes_the_app(monkeypatch: pytest.MonkeyPatch) -> None:
    """Running the CLI module invokes the application assembled at module scope."""
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(App, "__call__", lambda self: calls.append(self.name))

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        runpy.run_module("chefe.cli", run_name="__main__")

    assert calls == [("chefe",)]


def test_workspace_root_discovered_from_subdir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A manager built from a nested cwd finds the workspace by walking up to the manifest.

    This is bug 3: running chefe from `packages/` died with "chefe.toml not found" because the
    root was the cwd and discovery never climbed. The no-arg `PackageManager()` that `cli.py`
    builds now discovers from cwd the way git finds `.git`, so a subdir run resolves the root.
    """
    conda_workspace(tmp_path)
    nested = tmp_path / "packages" / "deep" / "leaf"
    nested.mkdir(parents=True)
    assert Workspace.discover(nested) == tmp_path.resolve()
    monkeypatch.chdir(nested)
    discovered = PackageManager()
    assert discovered.workspace.root == tmp_path.resolve()
    assert discovered.workspace.load().workspace.name == "life"


def test_workspace_discovery_falls_back_to_start_when_no_manifest(tmp_path: Path) -> None:
    """With no manifest anywhere above, discovery returns the start dir so `init` can scaffold."""
    nested = tmp_path / "fresh"
    nested.mkdir()
    assert Workspace.discover(nested) == nested.resolve()


@pytest.mark.parametrize(
    ("shell_env", "expected"),
    [("/usr/bin/zsh", "zsh"), ("/bin/bash", "bash"), ("/usr/bin/fish", "fish")],
)
def test_completions_targets_the_login_shell_by_default(
    *, shell_env: str, expected: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no shell given, completions follow the basename of `$SHELL`."""
    monkeypatch.setenv("SHELL", shell_env)
    assert detect_shell(None) == expected


@pytest.mark.parametrize("shell_env", ["/bin/dash", "", "/usr/bin/elvish"])
def test_completions_fall_back_to_bash_for_unsupported_shells(
    shell_env: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unset or unsupported `$SHELL` still yields a usable (bash) script."""
    monkeypatch.setenv("SHELL", shell_env)
    assert detect_shell(None) == "bash"


def test_completions_command_prints_a_shell_script(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`chefe completions zsh` prints cyclopts' zsh script naming the chefe commands.

    This wires the roadmap's shell completions: the command closes over the built app and
    emits its native completion to stdout, so a user pipes it where their shell expects.
    """
    conda_workspace(tmp_path)
    app = build(PackageManager(root=tmp_path))
    with pytest.raises(SystemExit) as exit_info:
        app(["completions", "zsh"])
    assert exit_info.value.code in (0, None)
    out = capsys.readouterr().out
    assert "#compdef chefe" in out
    # the script enumerates real subcommands, proving it reflects the wired app
    assert "completions" in out and "install" in out
