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
from chefe.tree_report import TreeReport

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


def test_add_toolchain_dep_edits_manifest_and_provisions(
    workspace: Workspace, recording_backends: list[tuple[str, ...]]
) -> None:
    """A non-pixi language writes `[<language>.deps]`, then installs the crate right away."""
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
    verbs = [(c[0], c[1]) for c in recording_backends]
    assert ("Pixi", "add") not in verbs
    assert ("Cargo", "sync") in verbs


def test_add_nodejs_dep_is_runnable_immediately(
    workspace: Workspace, recording_backends: list[tuple[str, ...]]
) -> None:
    """`chefe add -l nodejs` runs the node install itself, so `chefe run <bin>` works without
    a separate `chefe install` (the manifest-only add left the package uninstalled)."""
    manager = workspace(
        """
        [deps]
        nodejs = "*"
        """
    )
    manager.add("@openai/codex", language="nodejs")
    assert manager.load().toolchains()["nodejs"].deps["@openai/codex"].version == "*"
    assert ("Node", "install") in [(c[0], c[1]) for c in recording_backends]


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


@pytest.mark.parametrize(("env", "target"), [("", "default"), ("research", "research")])
def test_upgrade_without_packages_refreshes_every_ecosystem_within_constraints(
    workspace: Workspace,
    recording_backends: list[tuple[str, ...]],
    env: str,
    target: str,
) -> None:
    """A broad upgrade refreshes runtimes, Python, Node, and Cargo without loosening bounds."""
    manager = workspace(
        """
        [deps]
        python = "*"
        nodejs = "*"
        rust = "*"

        [nodejs.deps]
        prettier = "<4"

        [rust.deps]
        ripgrep = "<15"
        """
    )

    manager.upgrade(env=env)

    assert ("Pixi", "update", "-e", target) in recording_backends
    assert ("Node", "update") in recording_backends
    assert any(
        call[:2] == ("Cargo", "install") and "ripgrep" in call for call in recording_backends
    )
    assert not any(call[1] == "upgrade" for call in recording_backends)


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


def test_run_leading_env_flag_selects_a_declared_environment(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`chefe run --env <name> <cmd>` runs `<cmd>` in the named `[envs.*]` env, threading
    the env through pixi as `run -e <name>` with the flag stripped from the command."""
    manager = workspace(
        """
        [deps]
        python = "*"

        [tasks]
        build = "echo build"

        [envs.gpu]
        no-default = true

        [envs.gpu.deps]
        python = "*"
        """
    )
    seen: list[tuple[str, ...]] = []
    monkeypatch.setattr(Pixi, "exit_code", lambda self, *a, **k: seen.append(a) or 0)
    manager.run("--env", "gpu", "build", "--flag")
    assert seen == [("run", "-e", "gpu", "build", "--flag")]


def test_run_unknown_env_fails_fast(workspace: Workspace) -> None:
    """An `--env` that names no declared `[envs.*]` table is rejected before reaching pixi."""
    manager = workspace("[deps]\npython = '*'\n")
    with pytest.raises(ChefeError, match="No environment `ghost` is declared"):
        manager.run("--env", "ghost", "python")


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
        manager.run(*argv)


def test_activation_recompiles_an_edited_manifest(
    workspace: Workspace, capsys: pytest.CaptureFixture[str]
) -> None:
    """An edit to `chefe.toml` after a sync is recompiled on the next activation, never stale.

    The bug this guards: a command read the already-compiled `.chefe/pixi.toml` and never noticed
    the manifest had changed, so a freshly added `[env]` var silently did not take effect until a
    manual `chefe sync`. `stale()` keys off the manifest content digest, so an edit recompiles.
    """
    manager = workspace("[deps]\npython = '*'\n")
    assert manager.stale() is False  # nothing compiled yet, first provisioning is install's job
    manager.sync()
    assert manager.stale() is False  # fresh right after a sync
    manager.manifest.write_text(manager.manifest.read_text() + '\n[env]\nFOO = "bar"\n')
    assert manager.stale() is True  # the edit is caught by the content digest
    with manager.activated():
        pass
    assert manager.stale() is False  # activation recompiled, so the marker matches again
    assert 'FOO = "bar"' in manager.pixi.manifest.read_text()  # the new var reached the compile
    assert "recompiling" in capsys.readouterr().out


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
    manager.glob.install("shared")
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

    manager.glob.add("ripgrep")
    manager.glob.remove("ripgrep", env="tools")
    manager.glob.list("rip", env="tools", json=True)

    assert seen == [
        ("add", "w", ("ripgrep",), ""),
        ("remove", "tools", ("ripgrep",), ""),
        ("list", "tools", "rip", True),
    ]


@pytest.mark.parametrize(
    ("call", "match"),
    [
        (lambda manager: manager.glob.add(), "No packages given"),
        (lambda manager: manager.glob.remove(), "No packages given"),
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


def test_tree_renders_a_null_version_path_dep_without_crashing(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An editable/path dep pixi lists with a null version renders as `(path)`, not a crash.

    pixi reports a local path/editable checkout (the house packages installed `editable = true`)
    with `version = null`, which used to fail `Installed` validation and take down `chefe tree`.
    The declared dep still reads as installed, shown as `(path)`.
    """
    monkeypatch.setattr(
        Pixi,
        "installed",
        lambda self, env: {
            "python": Installed(version="3.12.0", kind="conda", explicit=True),
            "lote": Installed(version=None, kind="pypi", explicit=True),
        },
    )
    monkeypatch.setattr(Node, "installed", lambda self, env: {})
    monkeypatch.setattr(Cargo, "installed", lambda self, env: {})
    manager = workspace(
        """
        [deps]
        python = ">=3.11"

        [python.deps]
        lote = "*"
        """
    )
    manager.tree("default")
    assert "(path)" in capsys.readouterr().out


def test_tree_normalizes_python_names_and_accepts_conda_resolution(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Python declarations match PEP 503 names and packages Pixi resolved from conda."""
    monkeypatch.setattr(
        Pixi,
        "installed",
        lambda self, env: {
            "types_networkx": Installed(version="3.6.1", kind="pypi", explicit=True),
            "httpx": Installed(version="0.28.1", kind="conda", explicit=True),
        },
    )
    monkeypatch.setattr(Node, "installed", lambda self, env: {})
    monkeypatch.setattr(Cargo, "installed", lambda self, env: {})
    manager = workspace(
        """
        [deps]
        python = "*"

        [python.deps]
        types-networkx = ">=3.6"
        httpx = ">=0.28"
        """
    )

    installed = manager.installed_by_source("default")

    assert installed["python"] == {"types-networkx": "3.6.1", "httpx": "0.28.1"}


@pytest.mark.parametrize(
    ("spec", "version", "bucket"),
    [(">=1.0", None, "missing"), (">=1.0", "1.5", "ok"), (">=2.0", "1.5", "drift")],
)
def test_row_status_buckets(spec: str, version: str | None, bucket: str) -> None:
    """row_status maps a declared-vs-installed pair to the right tally bucket."""
    assert TreeReport.row_status(spec, version)[2] == bucket


def test_tree_plan_reports_install_update_and_remove(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`chefe tree --plan` is a dry run: it names what an install would add, update, and remove.

    This advances the roadmap's `chefe tree` dry run. A declared-but-absent dep is an install, a
    drifted one an update, and an explicit installed dep no longer declared a removal, while a
    transitive (non-explicit) dep is left to the solver and never shows up as a removal.
    """
    monkeypatch.setattr(
        Pixi,
        "installed",
        lambda self, env: {
            "python": Installed(version="3.12.0", kind="conda", explicit=True),
            "ripgrep": Installed(version="13.0.0", kind="conda", explicit=True),
            "stale": Installed(version="1.0.0", kind="conda", explicit=True),
            "libfoo": Installed(version="9.9", kind="conda", explicit=False),
        },
    )
    monkeypatch.setattr(Node, "installed", lambda self, env: {})
    monkeypatch.setattr(Cargo, "installed", lambda self, env: {})
    manager = workspace(
        """
        [deps]
        python = ">=3.11"
        ripgrep = ">=14"
        numpy = ">=2"
        """
    )
    manager.tree("default", plan=True)
    out = capsys.readouterr().out
    assert "install would change" in out
    assert "install" in out and "numpy >=2" in out  # declared, absent
    assert "update" in out and "ripgrep 13.0.0 → >=14" in out  # declared, drifted
    assert "remove" in out and "stale" in out  # explicit, undeclared
    assert "libfoo" not in out  # transitive deps are the solver's, never planned for removal


def test_tree_plan_reports_up_to_date_when_matched(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `--plan` over a fully provisioned env reports no changes rather than an empty list."""
    monkeypatch.setattr(
        Pixi,
        "installed",
        lambda self, env: {"python": Installed(version="3.12.0", kind="conda", explicit=True)},
    )
    monkeypatch.setattr(Node, "installed", lambda self, env: {})
    monkeypatch.setattr(Cargo, "installed", lambda self, env: {})
    manager = workspace('[deps]\npython = ">=3.11"\n')
    manager.tree("default", plan=True)
    assert "up to date" in capsys.readouterr().out


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
