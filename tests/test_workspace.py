from collections.abc import Callable
from pathlib import Path

import pytest
from faker import Faker
from plumbum import local
from pytest_mock import MockerFixture

from chefe.backends import Cargo, Node, Pixi
from chefe.errors import ChefeError
from chefe.manager import PackageManager
from chefe.state import Installed

Workspace = Callable[[str], PackageManager]


def test_manager_root_is_absolute(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A relative root is resolved against the cwd, so the env bin dirs put on PATH stay valid once
    a backend runs from inside the env (a relative npm path would break after a cwd change)."""
    monkeypatch.chdir(tmp_path)
    manager = PackageManager(Path("project"))
    assert manager.root.is_absolute()
    assert manager.root == tmp_path / "project"
    assert manager.manifest.is_absolute() and manager.out.is_absolute()


def test_init_scaffolds_then_is_idempotent(tmp_path: Path, faker_instance: Faker) -> None:
    """init writes a starter manifest once and leaves an existing one untouched."""
    project, other = faker_instance.word(), faker_instance.word()
    manager = PackageManager(tmp_path)
    manager.init(project)
    text = (tmp_path / "chefe.toml").read_text()
    assert f'name = "{project}"' in text and "[deps]" in text
    manager.init(other)  # second call must not overwrite
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
    workspace: Workspace,
    body: str,
    package_location: str | None,
    manager_name: str | None,
) -> None:
    """sync always writes pixi.toml, and writes package.json only where Node needs it."""
    manager = workspace(body)
    manager.sync()
    assert manager.pixi.manifest.exists()
    assert (manager.out / "package.json").exists() is (package_location == "out")
    assert (manager.root / "package.json").exists() is (package_location == "root")
    if manager_name is None:
        return
    node = manager.node(manager.load())
    assert node.name == manager_name
    assert node.cwd() == (manager.root if package_location == "root" else manager.out)


def test_clean_removes_generated_env(workspace: Workspace) -> None:
    manager = workspace(
        """
        [deps]
        python = "*"
        """
    )
    manager.sync()
    assert manager.out.exists()
    manager.clean()
    assert not manager.out.exists()


def test_add_toolchain_dep_edits_manifest_without_subprocess(
    workspace: Workspace, recording_backends: list[tuple[str, ...]]
) -> None:
    """A non-pixi language writes `[<language>.deps]` after its runtime is declared."""
    manager = workspace(
        """
        [deps]
        python = "*"
        rust = "*"
        """
    )
    manager.add("ripgrep", language="rust", spec=">=14")
    text = manager.manifest.read_text()
    assert "[rust.deps]" in text
    assert 'rust = "*"' in text
    assert manager.load().toolchains()["rust"].deps["ripgrep"].version == ">=14"
    assert ("Pixi", "add") not in [(c[0], c[1]) for c in recording_backends]


@pytest.mark.parametrize(
    ("language", "spec", "expected"),
    [
        ("conda", "*", ("Pixi", "add", "requests")),
        ("python", ">=2", ("Pixi", "add", "--pypi", "requests>=2")),
    ],
)
def test_add_pixi_languages_go_through_pixi_and_pull(
    workspace: Workspace,
    recording_backends: list[tuple[str, ...]],
    monkeypatch: pytest.MonkeyPatch,
    language: str,
    spec: str,
    expected: tuple[str, ...],
) -> None:
    """Conda and Python adds go through pixi, then pull resolved versions back."""
    pulled: list[bool] = []
    monkeypatch.setattr(PackageManager, "pull", lambda self: pulled.append(True))
    manager = workspace(
        """
        [deps]
        python = "*"
        """
    )
    manager.add("requests", language=language, spec=spec)
    assert expected in recording_backends
    assert pulled == [True]


@pytest.mark.parametrize(
    ("body", "packages", "language", "env", "match", "absent"),
    [
        (
            """
            [deps]
            python = "*"
            """,
            ("ripgrep",),
            "rust",
            "",
            r"Language `rust` is not declared in \[deps\]",
            "[rust.deps]",
        ),
        (
            """
            [deps]
            python = "*"
            """,
            ("requests",),
            "pypi",
            "",
            r"Language `pypi` is not declared in \[deps\]",
            "",
        ),
        (
            """
            [deps]
            python = "*"
            """,
            ("requests",),
            "",
            "",
            r"Language `` is not declared in \[deps\]",
            "",
        ),
        (
            """
            [deps]
            python = "*"
            """,
            (),
            "conda",
            "",
            "No packages given",
            "",
        ),
        (
            """
            [deps]
            python = "*"
            """,
            ("prettier",),
            "nodejs",
            "frontend",
            r"Environment `frontend` does not exist.*\[envs.frontend.deps\]",
            "",
        ),
        (
            """
            [deps]
            python = "*"

            [envs.frontend.deps]
            python = "*"
            """,
            ("prettier",),
            "nodejs",
            "frontend",
            r"Language `nodejs` is not declared in \[envs.frontend.deps\]",
            "",
        ),
    ],
)
def test_add_reports_language_errors(
    workspace: Workspace,
    body: str,
    packages: tuple[str, ...],
    language: str,
    env: str,
    match: str,
    absent: str,
) -> None:
    manager = workspace(body)
    with pytest.raises(ChefeError, match=match):
        manager.add(*packages, language=language, env=env)
    if absent:
        assert absent not in manager.manifest.read_text()


@pytest.mark.parametrize(
    ("text", "match"),
    [
        (None, "chefe.toml not found"),
        ("[workspace\n", r"invalid TOML.*Expected"),
        ('[deps]\npython = "*"\n', "Field required"),
        (
            """
            [workspace]
            name = "w"

            [nodejs.deps]
            prettier = "*"
            """,
            r"\[deps\]",
        ),
        (
            """
            [workspace]
            name = "w"

            [dev.nodejs.deps]
            prettier = "*"
            """,
            r"\[dev.nodejs\] has no matching package",
        ),
        (
            """
            [workspace]
            name = "w"

            [on.linux-64.nodejs.deps]
            prettier = "*"
            """,
            r"\[on.linux-64.nodejs\] has no matching package",
        ),
        (
            """
            [workspace]
            name = "w"

            [envs.frontend.nodejs.deps]
            prettier = "*"
            """,
            r"\[envs.frontend.nodejs\] has no matching package",
        ),
        (
            """
            [workspace]
            name = "w"

            [envs.default.deps]
            python = "*"
            """,
            r"\[envs.default\] is reserved",
        ),
    ],
)
def test_load_reports_user_errors(tmp_path: Path, text: str | None, match: str) -> None:
    if text is not None:
        (tmp_path / "chefe.toml").write_text(text)
    with pytest.raises(ChefeError, match=match):
        PackageManager(tmp_path).load()


def test_remove_drops_from_manifest(
    workspace: Workspace, recording_backends: list[tuple[str, ...]]
) -> None:
    manager = workspace(
        """
        [deps]
        python = "*"
        ripgrep = "*"
        """
    )
    manager.remove("ripgrep")
    assert "ripgrep" not in manager.load().deps


def test_pull_mirrors_resolved_versions(workspace: Workspace) -> None:
    """pull reads the generated pixi.toml and bumps the manifest's declared versions."""
    manager = workspace(
        """
        [deps]
        python = ">=3.11"
        """
    )
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
    manager.install()
    verbs = {(c[0], c[1]) for c in recording_backends}
    assert {("Pixi", "install"), ("Node", "install"), ("Cargo", "sync")} <= verbs


def test_activate_writes_a_sourceable_script(workspace: Workspace, mocker: MockerFixture) -> None:
    """`chefe activate` writes `.chefe/activate.sh` embedding the pixi hook and pinned modules."""
    manager = workspace('[deps]\npython = "*"\n\n[modules]\nnvidia = "26.3"\ngcc = "15.2.0"\n')
    mocker.patch.object(
        Pixi,
        "shell_hook",
        side_effect=lambda self, env="default": "export PIXI_OK=1",
        autospec=True,
    )
    path = manager.activate()
    script = path.read_text()
    assert path == manager.out / "activate.sh"
    assert "export PIXI_OK=1" in script
    # the pinned default modules render, guarded so they no-op off-cluster.
    assert "module load nvidia/26.3 gcc/15.2.0" in script
    assert "command -v module" in script
    assert local["bash"]["-n", str(path)].run(retcode=None)[0] == 0


def test_install_activate_only_skips_package_install(
    workspace: Workspace, recording_backends: list[tuple[str, ...]]
) -> None:
    """`install --activate-only` refreshes activate.sh without touching any backend."""
    manager = workspace('[deps]\npython = "*"\n')
    manager.install(activate_only=True)
    assert not any(call[1] == "install" for call in recording_backends)
    assert (manager.out / "activate.sh").exists()


def test_node_backend_uses_the_named_manager(workspace: Workspace) -> None:
    """`PackageManager.node` builds a `Node` carrying the manifest's `[nodejs] manager` name,
    rooted in the env dir (the per-manager genericity itself lives in `test_backends`)."""
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
    node = manager.node(manager.load())
    assert node.name == "pnpm"
    assert node.cwd() == manager.out


def test_update_and_upgrade_and_shell_and_run(
    workspace: Workspace,
    recording_backends: list[tuple[str, ...]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The remaining pixi-driven verbs each reach the backend with their verb."""
    monkeypatch.setattr(PackageManager, "pull", lambda self: None)
    manager = workspace(
        """
        [deps]
        python = "*"

        [tasks]
        build = "echo build"
        """
    )
    manager.update()
    manager.upgrade("python")
    manager.shell()
    manager.run("build", "--flag")
    assert {"update", "upgrade", "shell", "run"} <= {c[1] for c in recording_backends}


@pytest.mark.parametrize("code", [0, 3, 5])
@pytest.mark.parametrize("verb", ["run", "shell"])
def test_passthrough_verbs_exit_with_the_inner_code(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch, verb: str, code: int
) -> None:
    """`run` and `shell` both propagate the inner command's exit status through the pixi
    exit-code seam, raising `SystemExit(code)` on failure and staying silent on success."""
    manager = workspace(
        """
        [deps]
        python = '*'

        [tasks]
        build = "echo build"
        """
    )
    monkeypatch.setattr(Pixi, "exit_code", lambda self, *a, **k: code)
    invoke = (lambda: manager.run("build")) if verb == "run" else manager.shell
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
    manager.sync()
    binary_dir = manager.node(manager.load()).binary_dir()
    binary_dir.mkdir(parents=True)
    binary = binary_dir / "qmd"
    binary.write_text("#!/bin/sh\n")
    binary.chmod(0o755)
    seen: list[tuple[str, bool]] = []

    def note(verb: str) -> None:
        seen.append((verb, str(binary_dir) in local.env["PATH"]))

    monkeypatch.setattr(Pixi, "exit_code", lambda self, verb, *a, **k: note(verb) or 0)
    manager.run("qmd", "--version")
    manager.shell()
    assert seen == [("run", True), ("shell", True)]


def test_run_missing_name_reports_task_or_executable(workspace: Workspace) -> None:
    """A missing `chefe run` target explains that the name can be a task or an executable."""
    manager = workspace("[deps]\npython = '*'\n")
    with pytest.raises(ChefeError, match="No task or executable named `missing-chefe-tool`"):
        manager.run("missing-chefe-tool")


def test_x_exits_with_the_inner_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`chefe x` preserves a failing ephemeral command's exit status."""
    monkeypatch.setattr(Pixi, "exec", lambda self, specs, args: 13)
    with pytest.raises(SystemExit) as exit_info:
        PackageManager(tmp_path).x("ruff")
    assert exit_info.value.code == 13


def test_global_install_builds_specs(
    workspace: Workspace, recording_backends: list[tuple[str, ...]]
) -> None:
    """global_install turns `[deps]` into conda specs and installs them into a shared env."""
    manager = workspace(
        """
        [deps]
        python = ">=3.11"
        ripgrep = "*"
        """
    )
    manager.global_install("shared")
    glob = next(c for c in recording_backends if c[1] == "shared")
    specs = glob[2]  # global_install passes the spec list as a single positional arg
    assert "python>=3.11" in specs and "ripgrep" in specs


def test_global_add_remove_and_list_use_workspace_default(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Global mutations default to the workspace name and pass explicit envs through."""
    manager = workspace("[deps]\npython = '*'\n")
    seen: list[tuple[str, str, tuple[str, ...] | str, bool | str]] = []

    monkeypatch.setattr(
        Pixi,
        "global_add",
        lambda self, name, packages: seen.append(("add", name, packages, "")),
    )
    monkeypatch.setattr(
        Pixi,
        "global_remove",
        lambda self, name, packages: seen.append(("remove", name, packages, "")),
    )
    monkeypatch.setattr(
        Pixi,
        "global_list",
        lambda self, name="", regex="", json=False, sort_by="": seen.append(
            ("list", name, regex, json)
        ),
    )

    manager.global_add("ripgrep")
    manager.global_remove("ripgrep", env="tools")
    manager.global_list("rip", env="tools", json=True)

    assert seen == [
        ("add", "w", ("ripgrep",), ""),
        ("remove", "tools", ("ripgrep",), ""),
        ("list", "tools", "rip", True),
    ]


@pytest.mark.parametrize(
    ("call", "match"),
    [
        (lambda manager: manager.global_add(), "No packages given"),
        (lambda manager: manager.global_remove(), "No packages given"),
    ],
)
def test_global_add_remove_require_packages(
    workspace: Workspace, call: Callable[[PackageManager], None], match: str
) -> None:
    """Global add and remove fail clearly when no package names are provided."""
    manager = workspace("[deps]\npython = '*'\n")
    with pytest.raises(ChefeError, match=match):
        call(manager)


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
    manager = workspace(
        """
        [deps]
        python = ">=3.11"
        ripgrep = "*"
        """
    )
    manager.tree("default")  # exercises ok / drift / missing buckets and the transitive count


@pytest.mark.parametrize(
    ("spec", "version", "bucket"),
    [(">=1.0", None, "missing"), (">=1.0", "1.5", "ok"), (">=2.0", "1.5", "drift")],
)
def test_row_status_buckets(spec: str, version: str | None, bucket: str) -> None:
    """row_status maps a declared-vs-installed pair to the right tally bucket."""
    assert PackageManager.row_status(spec, version)[2] == bucket


@pytest.mark.parametrize("dotenv", [True, False])
def test_sync_writes_the_dotenv_loader_only_when_enabled(tmp_path: Path, dotenv: bool) -> None:
    """`workspace.dotenv` controls the generated loader and its activation entry."""
    (tmp_path / "chefe.toml").write_text(
        f'[workspace]\nname = "w"\nplatforms = ["linux-64"]\ndotenv = {str(dotenv).lower()}\n'
        '\n[deps]\npython = "*"\n'
    )
    manager = PackageManager(tmp_path)
    manager.sync()
    assert (manager.out / "dotenv.sh").exists() is dotenv
    assert ('"dotenv.sh"' in manager.pixi.manifest.read_text()) is dotenv
