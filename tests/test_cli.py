import functools
import json
import runpy
import warnings
from collections.abc import Callable
from pathlib import Path

import pytest
from cyclopts import App
from pytest_subprocess import FakeProcess

from chefe.backends import Pixi
from chefe.cli import build, detect_shell
from chefe.manager import PackageManager

from .conftest import write_manifest

Recorder = Callable[..., None]

# Each CLI argv and the manager method it must delegate to (cli.py is pure wiring).
COMMANDS = [
    (["init", "proj"], "init"),
    (["sync"], "sync"),
    (["install", "serving"], "install"),
    (["activate"], "activate"),
    (["update"], "update"),
    (["clean"], "clean"),
    (["run", "build", "--", "-x"], "run"),
    (["x", "ruff", "check", "."], "x"),
    (["exec", "ruff", "check", "."], "x"),  # `exec` is the long alias of `x`
    (["shell"], "shell"),
    (["tree"], "tree"),
    (["add", "numpy", "-l", "python"], "add"),
    (["upgrade", "numpy"], "upgrade"),
    (["remove", "numpy"], "remove"),
    (["global", "install", "shared"], "glob.install"),
]


def recording_manager(seen: list[str]) -> PackageManager:
    """A manager whose every command records its name instead of doing work.

    Each override keeps the real method's signature (via ``functools.wraps``) so cyclopts
    still parses each command exactly as in production. A dotted target such as `glob.install`
    is patched on the named collaborator the manager owns, which the CLI registers directly.
    """
    manager = PackageManager()

    def spy(target: object, name: str, label: str) -> Recorder:
        @functools.wraps(getattr(target, name))
        def record(*args: object, **kwargs: object) -> None:
            seen.append(label)

        return record

    for _, label in COMMANDS:
        owner, _, attr = label.rpartition(".")
        target = getattr(manager, owner) if owner else manager
        setattr(target, attr, spy(target, attr, label))
    return manager


@pytest.mark.parametrize(("argv", "method"), COMMANDS, ids=[f"{c[0][0]}/{c[1]}" for c in COMMANDS])
def test_cli_delegates_to_manager(argv: list[str], method: str) -> None:
    """Every command parses and forwards exactly once to its manager method."""
    seen: list[str] = []
    app = build(recording_manager(seen))
    with pytest.raises(SystemExit) as exit_info:  # cyclopts exits 0 on success
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
    app = build(PackageManager(tmp_path))
    with pytest.raises(SystemExit) as exit_info:
        app(["add", "ripgrep", "-l", "rust"])
    assert exit_info.value.code == 1
    assert "Language `rust` is not declared in [deps]" in capsys.readouterr().out


def test_module_entrypoint_invokes_the_app(monkeypatch: pytest.MonkeyPatch) -> None:
    """Running the CLI module invokes the application assembled at module scope."""
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(App, "__call__", lambda self: calls.append(self.name))

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        runpy.run_module("chefe.cli", run_name="__main__")

    assert calls == [("chefe",)]


def existing_global_env(fp: FakeProcess, pixi: str, name: str) -> None:
    """Register `pixi global list --json` so the manager sees env ``name`` as already present."""
    fp.register([pixi, "global", "list", "--json"], stdout=json.dumps([{"name": name}]))


def empty_global_env(fp: FakeProcess, pixi: str) -> None:
    """Register `pixi global list --json` as empty, so the manager treats every env as missing."""
    fp.register([pixi, "global", "list", "--json"], stdout=json.dumps([]))


def conda_workspace(root: Path) -> None:
    """Drop a `chefe.toml` whose `[workspace] name` defaults the global env to `life`."""
    write_manifest = root / "chefe.toml"
    write_manifest.write_text('[workspace]\nname = "life"\nplatforms = ["linux-64"]\n[deps]\n')


@pytest.mark.parametrize(
    ("language", "tool", "expected"),
    [
        ("nodejs", "npm", ["install", "-g", "typescript"]),
        ("npm", "npm", ["install", "-g", "typescript"]),
        ("rust", "cargo", ["install", "--root", "{prefix}", "typescript"]),
        ("cargo", "cargo", ["install", "--root", "{prefix}", "typescript"]),
    ],
    ids=["nodejs", "npm-alias", "rust", "cargo-alias"],
)
def test_global_add_language_routes_to_the_right_backend(
    language: str,
    tool: str,
    expected: list[str],
    fp: FakeProcess,
    tool_paths: dict[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`chefe global add <pkg> -l <lang>` reaches the env's own pip/npm/cargo, never `pixi global`.

    This is bug 1: `global add` had no `-l`, so `-l nodejs` was swallowed as a package and handed
    to `pixi global add`, which rejected the leading hyphen. Each language must build the exact
    backend argv against the global env prefix instead.
    """
    monkeypatch.setenv("PIXI_HOME", str(tmp_path / "pixi"))
    conda_workspace(tmp_path)
    prefix = tmp_path / "pixi" / "envs" / "life"
    binary = str(prefix / "bin" / tool)
    existing_global_env(fp, tool_paths["pixi"], "life")
    fp.register([binary, fp.any()], stdout="")
    app = build(PackageManager(tmp_path))
    with pytest.raises(SystemExit) as exit_info:
        app(["global", "add", "typescript", "-l", language])
    assert exit_info.value.code in (0, None)
    rendered = [part.replace("{prefix}", str(prefix)) for part in expected]
    assert list(fp.calls[-1]) == [binary, *rendered]


def test_global_add_pypi_routes_to_env_pip(
    fp: FakeProcess, tool_paths: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`-l python`/`-l pypi` installs through the global env's own python `-m pip`."""
    monkeypatch.setenv("PIXI_HOME", str(tmp_path / "pixi"))
    conda_workspace(tmp_path)
    python = str(tmp_path / "pixi" / "envs" / "life" / "bin" / "python")
    existing_global_env(fp, tool_paths["pixi"], "life")
    fp.register([python, fp.any()], stdout="")
    app = build(PackageManager(tmp_path))
    with pytest.raises(SystemExit) as exit_info:
        app(["global", "add", "ruff", "-l", "python"])
    assert exit_info.value.code in (0, None)
    assert list(fp.calls[-1]) == [python, "-m", "pip", "install", "ruff"]


def test_global_add_conda_defaults_env_to_workspace_name(
    fp: FakeProcess, tool_paths: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no `-e`, a conda `global add` targets `workspace.name` (here `life`)."""
    monkeypatch.setenv("PIXI_HOME", str(tmp_path / "pixi"))
    conda_workspace(tmp_path)
    existing_global_env(fp, tool_paths["pixi"], "life")
    fp.register([tool_paths["pixi"], fp.any()], stdout="")
    app = build(PackageManager(tmp_path))
    with pytest.raises(SystemExit) as exit_info:
        app(["global", "add", "ripgrep"])
    assert exit_info.value.code in (0, None)
    assert list(fp.calls[-1]) == [
        tool_paths["pixi"],
        "global",
        "add",
        "--environment",
        "life",
        "ripgrep",
    ]


def test_global_add_conda_creates_missing_env(
    fp: FakeProcess, tool_paths: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A conda `global add` against a missing env creates it via `pixi global install`.

    This is bug 2: `global add` hard-errored with "Environment life doesn't exist" because it
    always used `pixi global add`, which needs a pre-existing env. The create verb is the fix.
    """
    monkeypatch.setenv("PIXI_HOME", str(tmp_path / "pixi"))
    conda_workspace(tmp_path)
    empty_global_env(fp, tool_paths["pixi"])
    fp.register([tool_paths["pixi"], fp.any()], stdout="")
    app = build(PackageManager(tmp_path))
    with pytest.raises(SystemExit) as exit_info:
        app(["global", "add", "ripgrep"])
    assert exit_info.value.code in (0, None)
    assert list(fp.calls[-1]) == [
        tool_paths["pixi"],
        "global",
        "install",
        "--environment",
        "life",
        "ripgrep",
    ]


def test_global_add_multiple_packages_in_one_call(
    fp: FakeProcess, tool_paths: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Several packages ride one `global add` invocation into a single pixi call."""
    monkeypatch.setenv("PIXI_HOME", str(tmp_path / "pixi"))
    conda_workspace(tmp_path)
    existing_global_env(fp, tool_paths["pixi"], "life")
    fp.register([tool_paths["pixi"], fp.any()], stdout="")
    app = build(PackageManager(tmp_path))
    with pytest.raises(SystemExit):
        app(["global", "add", "ripgrep", "fd-find", "bat"])
    assert list(fp.calls[-1])[-3:] == ["ripgrep", "fd-find", "bat"]


def test_global_add_unknown_language_is_a_clean_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An unsupported `-l` value fails with a listing of valid languages, not a pixi crash."""
    conda_workspace(tmp_path)
    app = build(PackageManager(tmp_path))
    with pytest.raises(SystemExit) as exit_info:
        app(["global", "add", "ripgrep", "-l", "haskell"])
    assert exit_info.value.code == 1
    assert "Unknown language `haskell`" in capsys.readouterr().out


def test_global_add_runtime_language_provisions_missing_env(
    fp: FakeProcess, tool_paths: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `-l nodejs` add against a missing env provisions the nodejs runtime, then runs npm.

    This was the last `global add` friction: a runtime add hard-stopped on a fresh env with a
    pointer to `chefe global install`. Now the env is created with its runtime on demand, so
    `chefe global add codex -l nodejs` is a single command, the conda `install`-verb create path
    extended to the runtime languages.
    """
    monkeypatch.setenv("PIXI_HOME", str(tmp_path / "pixi"))
    conda_workspace(tmp_path)
    npm = str(tmp_path / "pixi" / "envs" / "life" / "bin" / "npm")
    empty_global_env(fp, tool_paths["pixi"])
    fp.register([tool_paths["pixi"], fp.any()], stdout="")
    fp.register([npm, fp.any()], stdout="")
    app = build(PackageManager(tmp_path))
    with pytest.raises(SystemExit) as exit_info:
        app(["global", "add", "typescript", "-l", "nodejs"])
    assert exit_info.value.code in (0, None)
    provision = [tool_paths["pixi"], "global", "install", "--environment", "life", "nodejs"]
    assert provision in [list(call) for call in fp.calls]
    assert list(fp.calls[-1]) == [npm, "install", "-g", "typescript"]


def test_global_add_without_packages_is_a_clean_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`chefe global add` with no package names fails with usage, not an empty pixi call."""
    conda_workspace(tmp_path)
    app = build(PackageManager(tmp_path))
    with pytest.raises(SystemExit) as exit_info:
        app(["global", "add"])
    assert exit_info.value.code == 1
    assert "No packages given" in capsys.readouterr().out


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
    assert PackageManager.discover(nested) == tmp_path.resolve()
    monkeypatch.chdir(nested)
    discovered = PackageManager()
    assert discovered.root == tmp_path.resolve()
    assert discovered.load().workspace.name == "life"


def test_workspace_discovery_falls_back_to_start_when_no_manifest(tmp_path: Path) -> None:
    """With no manifest anywhere above, discovery returns the start dir so `init` can scaffold."""
    nested = tmp_path / "fresh"
    nested.mkdir()
    assert PackageManager.discover(nested) == nested.resolve()


@pytest.mark.parametrize(
    ("shell_env", "expected"),
    [("/usr/bin/zsh", "zsh"), ("/bin/bash", "bash"), ("/usr/bin/fish", "fish")],
)
def test_completions_targets_the_login_shell_by_default(
    shell_env: str, expected: str, monkeypatch: pytest.MonkeyPatch
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
    app = build(PackageManager(tmp_path))
    with pytest.raises(SystemExit) as exit_info:
        app(["completions", "zsh"])
    assert exit_info.value.code in (0, None)
    out = capsys.readouterr().out
    assert "#compdef chefe" in out
    # the script enumerates real subcommands, proving it reflects the wired app
    assert "completions" in out and "install" in out


def run_workspace(root: Path, body: str = '[tasks]\nbuild = "echo build"\n') -> None:
    """Drop a manifest declaring the `build` task the `run` passthrough tests invoke."""
    write_manifest(root, body)


def recording_exit_code(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, ...]]:
    """Stub `Pixi.exit_code` with a success recorder and return its call list."""
    seen: list[tuple[str, ...]] = []
    monkeypatch.setattr(Pixi, "exit_code", lambda self, *args, **flags: seen.append(args) or 0)
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
    app = build(PackageManager(tmp_path))
    with pytest.raises(SystemExit) as exit_info:
        app(["run", "build", "--help"])
    assert exit_info.value.code in (0, None)
    assert seen == [("run", "-e", "default", "build", "--help")]


@pytest.mark.parametrize("flag", ["--help", "-h"])
def test_run_without_a_target_still_prints_its_own_help(
    flag: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A help flag with no task name keeps printing the run command's own page."""
    run_workspace(tmp_path)
    app = build(PackageManager(tmp_path))
    with pytest.raises(SystemExit) as exit_info:
        app(["run", flag])
    assert exit_info.value.code in (0, None)
    out = capsys.readouterr().out
    assert "chefe run" in out
    assert "task or installed executable" in out


def test_root_help_is_untouched(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """`chefe --help` still prints the app's own page listing the commands."""
    run_workspace(tmp_path)
    app = build(PackageManager(tmp_path))
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
        [tasks]
        build = "echo build"

        [envs.gpu]
        no-default = true

        [envs.gpu.deps]
        python = "*"
        """,
    )
    seen = recording_exit_code(monkeypatch)
    app = build(PackageManager(tmp_path))
    with pytest.raises(SystemExit) as exit_info:
        app(["run", "-e", "gpu", "build", "--help"])
    assert exit_info.value.code in (0, None)
    assert seen == [("run", "-e", "gpu", "build", "--help")]
