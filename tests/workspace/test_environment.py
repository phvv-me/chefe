import os
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest
from faker import Faker
from plumbum import local

from chefe.core import ChefeError
from chefe.manager import PackageManager
from chefe.manifest import Manifest

Workspace = Callable[[str], PackageManager]
LockedWorkspace = Callable[..., tuple[PackageManager, str]]


def test_manager_root_is_absolute(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A relative root is resolved against the cwd.

    The env bin dirs put on PATH then stay valid once a backend runs from inside the env, where
    a relative npm path would break after a cwd change.
    """
    monkeypatch.chdir(tmp_path)
    manager = PackageManager(root=Path("project"))
    assert manager.workspace.root.is_absolute()
    assert manager.workspace.root == tmp_path / "project"
    assert manager.workspace.manifest.is_absolute() and manager.workspace.out.is_absolute()


def test_init_scaffolds_then_is_idempotent(tmp_path: Path, faker_instance: Faker) -> None:
    """init writes a starter manifest once and leaves an existing one untouched."""
    project, other = faker_instance.word(), faker_instance.word()
    manager = PackageManager(root=tmp_path)
    manager.environment.init(project)
    text = (tmp_path / "chefe.toml").read_text()
    assert f'name = "{project}"' in text and "[deps]" in text
    manager.environment.init(other)
    assert (tmp_path / "chefe.toml").read_text() == text


@pytest.mark.parametrize(
    ("body", "package_location", "manager_name"),
    [
        (
            """
            [deps]
            python = ">=3.11"
            nodejs = "*"

            [nodejs.deps]
            leftpad = "*"
            """,
            "out",
            "npm",
        ),
        (
            """
            [deps]
            python = ">=3.11"
            """,
            None,
            None,
        ),
        (
            """
            [deps]
            nodejs = "*"

            [nodejs]
            app = true

            [nodejs.deps]
            svelte = ">=5"
            """,
            "root",
            "npm",
        ),
        (
            """
            [deps]
            nodejs = "*"

            [nodejs]
            manager = "pnpm"

            [nodejs.dev.deps]
            qmd = "*"
            """,
            "out",
            "pnpm",
        ),
    ],
    ids=["tooling-node", "pixi-only", "node-app", "node-dev-manager"],
)
def test_sync_package_json_location(
    *,
    workspace: Workspace,
    body: str,
    package_location: str | None,
    manager_name: str | None,
) -> None:
    """sync always writes pixi.toml, and writes package.json only where Node needs it."""
    manager = workspace(body)
    manager.environment.sync()
    assert manager.pixi.manifest.exists()
    assert (manager.workspace.out / "package.json").exists() is (package_location == "out")
    assert (manager.workspace.root / "package.json").exists() is (package_location == "root")
    if manager_name is None:
        return
    node = manager.environment.runtime.node("default")
    assert node.name == manager_name
    assert node.cwd() == (
        manager.workspace.root if package_location == "root" else manager.workspace.out
    )


def test_clean_removes_generated_env(workspace: Workspace) -> None:
    manager = workspace(
        """
        [deps]
        python = "*"
        """
    )
    manager.environment.sync()
    assert manager.workspace.out.exists()
    manager.environment.clean()
    assert not manager.workspace.out.exists()


def test_sync_leaves_identical_pixi_manifest_mtime_unchanged(workspace: Workspace) -> None:
    """An identical `chefe sync` is a true no-op for the compiled Pixi manifest."""
    manager = workspace('[deps]\npython = "*"\n')
    manager.environment.sync()
    target = manager.pixi.manifest
    fixed = 1_700_000_000_123_456_789
    os.utime(target, ns=(fixed, fixed))

    manager.environment.sync()

    assert target.stat().st_mtime_ns == fixed


def test_sync_marks_a_lock_stale_when_serving_resolution_inputs_change(
    locked_workspace: LockedWorkspace,
) -> None:
    """An editable dep, URL wheel, and raised Python floor cannot retain the older lock."""
    original = """
        [workspace]
        name = "w"
        platforms = ["linux-64", "linux-aarch64"]

        [envs.serving]
        no-default = true
        platforms = ["linux-64", "linux-aarch64"]

        [envs.serving.deps]
        python = ">=3.12,<3.14"

        [envs.serving.python.deps]
        patos = { path = "packages/patos", editable = true }

        [envs.serving.on.linux-aarch64.python.deps]
        vllm = { url = "https://wheels.example/vllm-aarch64.whl" }
        """
    manager, compiled = locked_workspace(original, env="serving")
    manager.workspace.manifest.write_text(original.replace(">=3.12,<3.14", ">=3.13,<3.14"))
    manager.environment.sync("serving")

    refreshed = manager.pixi.manifest.read_text()
    carried = [
        'python = ">=3.13,<3.14"',
        'path = "../packages/patos"',
        'url = "https://wheels.example/vllm-aarch64.whl"',
    ]
    assert compiled != refreshed
    assert all(fragment in refreshed for fragment in carried)
    # The lock survives so other processes sharing this checkout keep a usable environment,
    # and the marker is what makes a later `install` demand `--resolve`.
    assert manager.pixi.lock.read_text() == "version: 7\n"
    assert (manager.workspace.out / ".resolution-stale").exists()


def test_sync_preserves_a_lock_when_the_compiled_manifest_is_identical(
    workspace: Workspace,
) -> None:
    """An idempotent sync keeps the verified generated pair intact."""
    manager = workspace('[deps]\npython = "*"\n')
    manager.environment.sync()
    manager.pixi.lock.write_text("version: 7\n")

    manager.environment.sync()

    assert manager.pixi.lock.read_text() == "version: 7\n"


def test_sync_preserves_a_lock_when_only_a_task_changes(workspace: Workspace) -> None:
    """A task edit recompiles Pixi without forcing an unrelated dependency solve."""
    manager = workspace(
        """
        [deps]
        python = "*"

        [tasks]
        check = "python -m pytest"
        """
    )
    manager.environment.sync()
    original = manager.pixi.manifest.read_text()
    manager.pixi.lock.write_text("version: 7\n")

    changed = manager.workspace.manifest.read_text().replace(
        "python -m pytest", "python -m pytest -q"
    )
    manager.workspace.manifest.write_text(changed)
    manager.environment.sync()

    assert manager.pixi.manifest.read_text() != original
    assert manager.pixi.lock.read_text() == "version: 7\n"


def test_sync_marks_a_lock_stale_when_local_project_identity_changes(
    tmp_path: Path, locked_workspace: LockedWorkspace
) -> None:
    """Replacing a project at one path cannot retain its former distribution identity."""
    metadata = tmp_path / "packages" / "archy" / "pyproject.toml"
    metadata.parent.mkdir(parents=True)
    metadata.write_text('[project]\nname = "legacy-archy"\nversion = "0.1.0"\n')
    project, compiled = locked_workspace(
        """
        [workspace]
        name = "w"
        platforms = ["linux-64"]

        [deps]
        python = "*"

        [python.deps]
        archy = { path = "packages/archy", editable = true }
        """
    )

    metadata.write_text('[project]\nname = "archy"\nversion = "0.41.0"\n')
    project.environment.sync()

    assert project.pixi.manifest.read_text() == compiled
    assert project.pixi.lock.read_text() == "version: 7\n"
    assert (project.workspace.out / ".resolution-stale").exists()


def test_install_drives_every_backend(
    workspace: Workspace, recording_backends: Sequence[tuple[str, ...]]
) -> None:
    """install syncs then fans out to pixi install, npm install, and a cargo sync."""
    manager = workspace(
        """
        [deps]
        python = "*"
        nodejs = "*"
        rust = "*"

        [nodejs.dev.deps]
        qmd = "*"

        [rust.deps]
        rg = "*"
        """
    )
    manager.environment.install()
    verbs = {(c[0], c[1]) for c in recording_backends}
    assert {("Pixi", "install"), ("Node", "install"), ("Cargo", "sync")} <= verbs


def test_install_refuses_a_stale_lock_without_resolve(
    workspace: Workspace, recording_backends: Sequence[tuple[str, ...]]
) -> None:
    """A lock the manifest has outgrown blocks install rather than being deleted underneath it.

    Several agents share one checkout here, so deleting the lock would take every other process
    down until somebody finished solving. Refusing keeps the old environment usable meanwhile.
    """
    manager = workspace('[deps]\npython = "*"\n')
    manager.environment.install()
    manager.pixi.lock.write_text("version: 7\n")
    grown = manager.workspace.manifest.read_text().replace(
        'python = "*"', 'python = "*"\nripgrep = "*"'
    )
    manager.workspace.manifest.write_text(grown)

    with pytest.raises(ChefeError, match="no longer matches the resolution inputs"):
        manager.environment.install()

    assert manager.pixi.lock.read_text() == "version: 7\n"
    manager.environment.install(resolve=True)
    assert not (manager.workspace.out / ".resolution-stale").exists()


def test_install_activate_only_skips_package_install(
    workspace: Workspace, recording_backends: Sequence[tuple[str, ...]]
) -> None:
    """`install --activate-only` refreshes activate.sh without touching any backend."""
    manager = workspace('[deps]\npython = "*"\n')
    manager.environment.install(activate_only=True)
    assert not any(call[1] == "install" for call in recording_backends)
    assert (manager.workspace.out / "activate.sh").exists()


def test_install_resolve_threads_the_explicit_solve_permission(
    workspace: Workspace, recording_backends: Sequence[tuple[str, ...]]
) -> None:
    """`install --resolve` reaches Pixi as an explicit permission to refresh the lock."""
    manager = workspace('[deps]\npython = "*"\n')

    manager.environment.install(resolve=True)

    assert ("Pixi", "install", "--resolve", "-e", "default") in recording_backends


def test_activation_recompiles_an_edited_manifest(
    workspace: Workspace, capsys: pytest.CaptureFixture[str]
) -> None:
    """An edit to `chefe.toml` after a sync is recompiled on the next activation, never stale.

    The bug this guards: a command read the already-compiled `.chefe/pixi.toml` and never noticed
    the manifest had changed, so a freshly added `[env]` var silently did not take effect until a
    manual `chefe sync`. `stale()` keys off the manifest content digest, so an edit recompiles.
    """
    manager = workspace("[deps]\npython = '*'\n")
    # First provisioning is install's job, so an uncompiled workspace must never read stale.
    assert manager.environment.compiler.stale() is False
    manager.environment.sync()
    assert manager.environment.compiler.stale() is False
    manager.workspace.manifest.write_text(
        manager.workspace.manifest.read_text() + '\n[env]\nFOO = "bar"\n'
    )
    assert manager.environment.compiler.stale() is True
    with manager.environment.runtime.activated():
        assert manager.environment.compiler.stale() is False
    assert 'FOO = "bar"' in manager.pixi.manifest.read_text()
    assert "recompiling" in capsys.readouterr().out


def test_sync_keeps_a_mid_compile_manifest_edit_stale(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A manifest edit during compilation cannot bless output built from prior content."""
    manager = workspace("[deps]\npython = '*'\n")
    load = manager.workspace.load

    def load_then_edit() -> Manifest:
        manifest = load()
        manager.workspace.manifest.write_text(
            manager.workspace.manifest.read_text() + '\n[env]\nFOO = "bar"\n'
        )
        return manifest

    monkeypatch.setattr(manager.workspace, "load", load_then_edit)
    manager.environment.sync()

    assert manager.environment.compiler.stale() is True
    assert 'FOO = "bar"' not in manager.pixi.manifest.read_text()


@pytest.mark.parametrize("dotenv", [True, False])
def test_sync_writes_the_dotenv_loader_only_when_enabled(*, tmp_path: Path, dotenv: bool) -> None:
    """`workspace.dotenv` controls the generated loader and its activation entry."""
    (tmp_path / "chefe.toml").write_text(
        f'[workspace]\nname = "w"\nplatforms = ["linux-64"]\ndotenv = {str(dotenv).lower()}\n'
        '\n[deps]\npython = "*"\n'
    )
    manager = PackageManager(root=tmp_path)
    manager.environment.sync()
    assert (manager.workspace.out / "dotenv.sh").exists() is dotenv
    assert ('"dotenv.sh"' in manager.pixi.manifest.read_text()) is dotenv


def test_dotenv_loader_states_its_precedence_rule(workspace: Workspace) -> None:
    """The generated loader snapshots the exported environment before sourcing `.env`.

    That snapshot is what lets a pre-existing export win over a value the file carries, so its
    presence (and the one-line rule comment) is pinned here as the behavioral contract.
    """
    manager = workspace('[deps]\npython = "*"\n')
    manager.environment.sync()
    script = (manager.workspace.out / "dotenv.sh").read_text()
    assert "already exported in the shell wins" in script
    assert 'export -p > "$snapshot"' in script
    assert '. "$snapshot" 2>/dev/null || true' in script


def test_dotenv_loader_lets_the_shell_win_and_fills_gaps_from_the_file(
    workspace: Workspace,
) -> None:
    """A pre-exported var survives sourcing `.env`; an unset var is filled in from the file.

    This runs the generated script under a real bash, since the precedence trick (snapshot,
    source, restore) is only proven correct by executing it, not by reading its text.
    """
    manager = workspace('[deps]\npython = "*"\n')
    manager.environment.sync()
    (manager.workspace.root / ".env").write_text(
        'EXISTING_VAR="from dotenv file"\nNEW_VAR="from dotenv file"\n'
    )
    probe = 'source ./dotenv.sh; printf "%s|%s" "$EXISTING_VAR" "$NEW_VAR"'
    with local.cwd(manager.workspace.out), local.env(EXISTING_VAR="from shell"):
        output = local["bash"]["-c", probe]()
    assert output == "from shell|from dotenv file"
