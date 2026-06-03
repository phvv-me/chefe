from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from faker import Faker

from chefe.backends import Cargo, Node, Pixi
from chefe.manager import PackageManager
from chefe.state import Installed

Workspace = Callable[[str], PackageManager]


def test_init_scaffolds_then_is_idempotent(tmp_path: Path, faker_instance: Faker) -> None:
    """init writes a starter manifest once and leaves an existing one untouched."""
    project, other = faker_instance.word(), faker_instance.word()
    manager = PackageManager(tmp_path)
    manager.init(project)
    text = (tmp_path / "chefe.toml").read_text()
    assert f'name = "{project}"' in text and "[deps]" in text
    manager.init(other)  # second call must not overwrite
    assert (tmp_path / "chefe.toml").read_text() == text


def test_sync_writes_pixi_and_package_json(workspace: Workspace) -> None:
    """sync compiles pixi.toml always, and a tooling package.json under .chefe for npm deps."""
    manager = workspace('[deps]\npython = ">=3.11"\n[npm.deps]\nleftpad = "*"\n')
    manager.sync()
    assert manager.pixi.manifest.exists()
    assert (manager.out / "package.json").exists()


def test_sync_skips_package_json_without_npm(workspace: Workspace) -> None:
    manager = workspace('[deps]\npython = ">=3.11"\n')
    manager.sync()
    assert not (manager.out / "package.json").exists()


def test_app_mode_syncs_package_json_at_the_project_root(workspace: Workspace) -> None:
    """`[npm] app` writes package.json and resolves the driver at the root, not under .chefe."""
    manager = workspace('[npm]\napp = true\n[npm.deps]\nsvelte = ">=5"\n')
    manager.sync()
    assert (manager.root / "package.json").exists()  # where Vite resolves node_modules
    assert not (manager.out / "package.json").exists()  # not the tooling location
    assert manager.node(manager.load()).out == manager.root


def test_clean_removes_generated_env(workspace: Workspace) -> None:
    manager = workspace('[deps]\npython = "*"\n')
    manager.sync()
    assert manager.out.exists()
    manager.clean()
    assert not manager.out.exists()


def test_add_cargo_edits_manifest_without_subprocess(
    workspace: Workspace, recording_backends: list[tuple[str, ...]]
) -> None:
    """A cargo add is a pure Document edit (pixi never resolves it), then a sync."""
    manager = workspace('[deps]\npython = "*"\n')
    manager.add("ripgrep", cargo=True, spec=">=14")
    assert "[cargo.deps]" in manager.manifest.read_text()
    assert manager.load().cargo.deps["ripgrep"].version == ">=14"
    assert ("Pixi", "add") not in [(c[0], c[1]) for c in recording_backends]


def test_add_pypi_goes_through_pixi_and_pull(
    workspace: Workspace,
    recording_backends: list[tuple[str, ...]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pypi add syncs, calls `pixi add --pypi`, then pulls resolved versions back."""
    pulled: list[bool] = []
    monkeypatch.setattr(PackageManager, "pull", lambda self: pulled.append(True))
    manager = workspace('[deps]\npython = "*"\n')
    manager.add("requests", pypi=True)
    assert ("Pixi", "add") in [(c[0], c[1]) for c in recording_backends]
    assert pulled == [True]


def test_remove_drops_from_manifest(
    workspace: Workspace, recording_backends: list[tuple[str, ...]]
) -> None:
    manager = workspace('[deps]\npython = "*"\nripgrep = "*"\n')
    manager.remove("ripgrep")
    assert "ripgrep" not in manager.load().deps


def test_pull_mirrors_resolved_versions(workspace: Workspace) -> None:
    """pull reads the generated pixi.toml and bumps the manifest's declared versions."""
    manager = workspace('[deps]\npython = ">=3.11"\n')
    manager.sync()
    manager.pixi.manifest.write_text(
        '[workspace]\nname = "w"\n\n[dependencies]\npython = "3.12.5"\n'
    )
    manager.pull()
    assert manager.load().deps["python"].version == "3.12.5"


def test_install_drives_every_backend(
    workspace: Workspace, recording_backends: list[tuple[str, ...]]
) -> None:
    """install syncs then fans out to pixi install, npm install, and a cargo sync."""
    manager = workspace('[deps]\npython = "*"\n[cargo.deps]\nrg = "*"\n')
    manager.install()
    verbs = {(c[0], c[1]) for c in recording_backends}
    assert {("Pixi", "install"), ("Node", "install"), ("Cargo", "sync")} <= verbs


def test_node_backend_is_generic_over_the_manager_name(workspace: Workspace) -> None:
    """`[npm] manager` is any binary name; the backend runs it in the env dir, no code per tool."""
    for name in ("npm", "pnpm", "bun", "aube", "deno"):
        manager = workspace(f'[npm]\nmanager = "{name}"\n[npm.deps]\nx = "*"\n')
        node = manager.node(manager.load())
        assert node.name == name
        assert node.cwd() == manager.out


def test_update_and_upgrade_and_shell_and_run(
    workspace: Workspace,
    recording_backends: list[tuple[str, ...]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The remaining pixi-driven verbs each reach the backend with their verb."""
    monkeypatch.setattr(PackageManager, "pull", lambda self: None)
    manager = workspace('[deps]\npython = "*"\n')
    manager.update()
    manager.upgrade("python")
    manager.shell()
    manager.run("build", "--flag")
    assert {"update", "upgrade", "shell", "run"} <= {c[1] for c in recording_backends}


def test_global_install_builds_specs(
    workspace: Workspace, recording_backends: list[tuple[str, ...]]
) -> None:
    """global_install turns `[deps]` into conda specs and installs them into a shared env."""
    manager = workspace('[deps]\npython = ">=3.11"\nripgrep = "*"\n')
    manager.global_install("shared")
    glob = next(c for c in recording_backends if c[1] == "shared")
    specs = glob[2]  # global_install passes the spec list as a single positional arg
    assert "python>=3.11" in specs and "ripgrep" in specs


def test_x_runs_ephemeral(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """x runs a throwaway command through the pixi exec seam, with no manifest needed."""
    seen: list[tuple[tuple[str, ...], tuple[str, ...]]] = []
    monkeypatch.setattr(Pixi, "exec", lambda self, specs, args: bool(seen.append((specs, args))))
    PackageManager(tmp_path).x("ruff", "check", ".", with_=("ruff",))
    assert seen == [(("ruff",), ("ruff", "check", "."))]


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
    manager = workspace('[deps]\npython = ">=3.11"\nripgrep = "*"\n')
    manager.tree("default")  # exercises ok / drift / missing buckets and the transitive count


@pytest.mark.parametrize(
    ("spec", "version", "bucket"),
    [(">=1.0", None, "missing"), (">=1.0", "1.5", "ok"), (">=2.0", "1.5", "drift")],
)
def test_row_status_buckets(spec: str, version: str | None, bucket: str) -> None:
    """row_status maps a declared-vs-installed pair to the right tally bucket."""
    assert PackageManager.row_status(spec, version)[2] == bucket
