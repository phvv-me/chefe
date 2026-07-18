import json
from collections.abc import Callable
from pathlib import Path

import pytest
from plumbum import local
from plumbum.commands.processes import CommandNotFound
from pytest_mock import MockerFixture
from pytest_subprocess import FakeProcess

from chefe.backends import Cargo, Node, Pixi, Tool
from chefe.errors import ChefeError
from chefe.manager import PackageManager
from chefe.manifest import Spec
from chefe.state import Installed
from chefe.utils import current_platform


def test_current_platform_shape() -> None:
    """The host platform reads as `<os>-<arch>` from the known os/arch maps."""
    osname, arch = current_platform().split("-", 1)
    assert osname in ("osx", "linux", "win")
    assert arch in ("64", "arm64", "aarch64")


def test_tool_default_scope_is_empty_and_available() -> None:
    """The base backend pins nothing and runs by default; pixi overrides scope."""
    assert Tool().scope() == () and Tool().available() is True


def test_flags_translate_kwargs_to_cli_args() -> None:
    """Booleans become bare `--flag`, values become `--flag value`, falsy ones drop, `_`→`-`."""
    assert Tool.flags(pypi=True, cargo=False, npm=None) == ("--pypi",)
    assert Tool.flags(feature="serving", env="") == ("--feature", "serving")
    assert Tool.flags(no_default=True) == ("--no-default",)


def test_tool_skips_when_unavailable() -> None:
    """A backend whose `available()` is False is a silent no-op, running nothing."""

    class Blocked(Tool):
        name = "nonexistent-binary"

        def available(self) -> bool:
            return False

    assert Blocked()("install") is None
    assert Blocked().exit_code("install") == 0


@pytest.mark.parametrize("code", [0, 1, 2, 42, 255])
def test_passthrough_preserves_exit_code(
    code: int, fp: FakeProcess, tool_paths: dict[str, str]
) -> None:
    """A command's exact exit code rides back out of `passthrough`, zero for a clean success."""
    fp.register([tool_paths["pixi"], fp.any()], returncode=code)
    assert Tool.passthrough(local[tool_paths["pixi"]]["run"]) == code


@pytest.mark.parametrize("code", [0, 7])
def test_exit_code_threads_the_real_command_code(
    code: int, fp: FakeProcess, tmp_path: Path, tool_paths: dict[str, str]
) -> None:
    """`exit_code` runs the backend through its real seam and returns the command's own code."""
    fp.register([tool_paths["pixi"], fp.any()], returncode=code)
    assert Pixi(tmp_path).exit_code("run", "task") == code


def test_node_available_requires_package_json(tmp_path: Path) -> None:
    """The JS backend refuses to run until a `package.json` exists in the env dir."""
    node = Node(tmp_path)
    assert node.available() is False
    (tmp_path / "package.json").write_text("{}")
    assert node.available() is True


def test_node_installed_reads_node_modules(tmp_path: Path) -> None:
    """`installed` discovers both plain and scoped packages under node_modules."""
    for rel, name, version in (
        ("node_modules/prettier", "prettier", "3.2.0"),
        ("node_modules/@scope/pkg", "@scope/pkg", "1.0.0"),
    ):
        directory = tmp_path / rel
        directory.mkdir(parents=True)
        (directory / "package.json").write_text(json.dumps({"name": name, "version": version}))
    found = Node(tmp_path).installed("default")
    assert found["prettier"].version == "3.2.0"
    assert found["@scope/pkg"].kind == "npm"


@pytest.mark.parametrize("manager", ["npm", "pnpm", "yarn", "aube"])
def test_node_runs_the_named_manager_in_the_env_dir(
    manager: str, fp: FakeProcess, tmp_path: Path, tool_paths: dict[str, str]
) -> None:
    """The JS backend invokes whatever manager it is named, targeting the env dir by cwd.

    The same call shape works for every tool, so a new package manager needs no code, only a name.
    """
    (tmp_path / "package.json").write_text("{}")
    node = Node(tmp_path, manager)
    assert node.name == manager and node.cwd() == tmp_path
    fp.register([tool_paths[manager], fp.any()], stdout="")
    node("install")
    assert list(fp.calls[-1]) == [tool_paths[manager], "install"]


def test_cargo_installed_parses_crates_toml(tmp_path: Path) -> None:
    """`installed` reads versions from `.crates.toml`, and an absent file yields nothing."""
    cargo = Cargo(tmp_path, Pixi(tmp_path))
    root = cargo.root("default")
    root.mkdir(parents=True)
    (root / ".crates.toml").write_text('[v1]\n"ripgrep 14.1.0 (registry+https://x)" = ["rg"]\n')
    found = cargo.installed("default")
    assert found["ripgrep"].version == "14.1.0"
    assert cargo.installed("missing") == {}


def test_cargo_installed_skips_malformed_crate_keys(tmp_path: Path) -> None:
    """A `.crates.toml` key missing its version is skipped, not crashed on.

    A well-formed key reads `"name version (source)"`; a stray single-token key used to index
    past the split's end and raise `IndexError`, taking down `chefe tree` and `chefe install`
    on an otherwise healthy env. The malformed entry is now dropped and the good one survives.
    """
    cargo = Cargo(tmp_path, Pixi(tmp_path))
    root = cargo.root("default")
    root.mkdir(parents=True)
    (root / ".crates.toml").write_text(
        '[v1]\n"ripgrep 14.1.0 (registry+https://x)" = ["rg"]\n"orphan" = ["x"]\n'
    )
    found = cargo.installed("default")
    assert found == {"ripgrep": Installed(version="14.1.0", kind="cargo")}


def test_cargo_sync_reconciles_declared_against_installed(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """sync makes the env's crates match the declaration through `pixi run cargo`, pinned to the
    synced env: it uninstalls crates no longer declared, installs declared-but-missing ones
    (with `--version` only for a real pin), reinstalls a drifted crate with `--force`, and
    skips a satisfied one. Each call carries `--environment <env>` so an env-scoped rust resolves.
    """
    pixi = Pixi(tmp_path)
    cargo = Cargo(tmp_path, pixi)
    mocker.patch.object(
        Cargo,
        "installed",
        return_value={
            "stale": Installed(version="1.0.0", kind="cargo"),
            "drift": Installed(version="0.1.0", kind="cargo"),
            "kept": Installed(version="2.0.0", kind="cargo"),
        },
        autospec=True,
    )
    calls: list[tuple[str, ...]] = []
    mocker.patch.object(
        Pixi,
        "__call__",
        side_effect=lambda self, verb, *args, **flags: calls.append(
            (verb, *Tool.flags(**flags), *args)
        ),
        autospec=True,
    )
    declared = {
        "fresh": Spec.model_validate(">=2.0"),
        "wild": Spec.model_validate("*"),
        "drift": Spec.model_validate(">=0.2"),
        "kept": Spec.model_validate("2.0.0"),
        "pinned": Spec.model_validate({"version": ">=0.1", "locked": True}),
    }
    cargo.sync("serving", declared)
    at = str(pixi.env_prefix("serving"))
    assert all(call[:3] == ("run", "--environment", "serving") for call in calls)
    bodies = [call[3:] for call in calls]
    assert ("cargo", "uninstall", "--root", at, "stale") in bodies
    assert ("cargo", "install", "--root", at, "--version", ">=2.0", "fresh") in bodies
    assert ("cargo", "install", "--root", at, "wild") in bodies  # `*` carries no `--version`
    assert ("cargo", "install", "--root", at, "--version", ">=0.2", "--force", "drift") in bodies
    assert ("cargo", "install", "--root", at, "--version", ">=0.1", "--locked", "pinned") in bodies
    assert not any("kept" in body for body in bodies)  # satisfied, skipped


def test_cargo_update_refreshes_even_satisfied_crates(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """update forces retained crates through Cargo so compatible releases are not skipped."""
    pixi = Pixi(tmp_path)
    cargo = Cargo(tmp_path, pixi)
    mocker.patch.object(
        Cargo,
        "installed",
        return_value={"ripgrep": Installed(version="14.0.0", kind="cargo")},
        autospec=True,
    )
    calls: list[tuple[str, ...]] = []
    mocker.patch.object(
        Pixi,
        "__call__",
        side_effect=lambda self, verb, *args, **flags: calls.append(
            (verb, *Tool.flags(**flags), *args)
        ),
        autospec=True,
    )

    cargo.update("default", {"ripgrep": Spec.model_validate("<15")})

    assert "--force" in calls[0]
    assert "--version" in calls[0]
    assert "<15" in calls[0]


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        (
            {"git": "https://x/r", "branch": "main"},
            ("--git", "https://x/r", "--branch", "main"),
        ),
        (
            {"version": ">=1", "path": "../crate"},
            ("--version", ">=1", "--path", "../crate"),
        ),
        (
            {"git": "https://x/r", "tag": "v1", "rev": "abc", "locked": True},
            ("--git", "https://x/r", "--tag", "v1", "--rev", "abc", "--locked"),
        ),
    ],
    ids=["git-branch", "version-path", "git-tag-rev-locked"],
)
def test_cargo_install_args_threads_source_overrides(
    spec: dict[str, object], expected: tuple[str, ...]
) -> None:
    """A crate's `git`/`path`/`branch`/`tag`/`rev`/`locked` ride through as their cargo flags,
    so a source-pinned crate installs exactly as declared instead of from the registry."""
    assert Cargo.install_args(Spec.model_validate(spec)) == expected


def test_pixi_scope_pins_manifest_path(tmp_path: Path) -> None:
    """The pixi backend injects `--manifest-path` so every call targets the env it owns."""
    pixi = Pixi(tmp_path)
    assert pixi.manifest == tmp_path / "pixi.toml"
    assert pixi.scope() == ("--manifest-path", str(pixi.manifest))


def test_pixi_installed_parses_list_json(
    fp: FakeProcess, tmp_path: Path, tool_paths: dict[str, str]
) -> None:
    """`installed` maps `pixi list --json` records into Installed entries."""
    pixi = Pixi(tmp_path)
    records = [
        {"name": "numpy", "version": "2.0.0", "kind": "conda", "is_explicit": True},
        {"name": "rich", "version": "13.7.0", "kind": "pypi", "is_explicit": False},
    ]
    fp.register(
        [
            tool_paths["pixi"],
            "list",
            "--manifest-path",
            str(pixi.manifest),
            "-e",
            "default",
            "--json",
        ],
        stdout=json.dumps(records),
    )
    found = pixi.installed("default")
    assert found["numpy"].kind == "conda" and found["numpy"].explicit
    assert found["rich"].explicit is False


def test_pixi_installed_tolerates_a_null_or_absent_version(
    fp: FakeProcess, tmp_path: Path, tool_paths: dict[str, str]
) -> None:
    """An editable/path dep pixi reports with a null (or missing) version must not crash `tree`.

    pixi emits ``"version": null`` for a local path/editable checkout (no registry pin), and the
    record may omit the key entirely; both map to an `Installed` whose version renders as `(path)`.
    """
    pixi = Pixi(tmp_path)
    records = [
        {"name": "lote", "version": None, "kind": "pypi", "is_explicit": True},
        {"name": "chefe", "kind": "pypi", "is_explicit": True},
    ]
    fp.register(
        [
            tool_paths["pixi"],
            "list",
            "--manifest-path",
            str(pixi.manifest),
            "-e",
            "default",
            "--json",
        ],
        stdout=json.dumps(records),
    )
    found = pixi.installed("default")
    assert found["lote"].version is None and found["lote"].shown_version == "(path)"
    assert found["chefe"].version is None and found["chefe"].shown_version == "(path)"


def test_pixi_shell_hook_returns_activation_script(
    fp: FakeProcess, tmp_path: Path, tool_paths: dict[str, str]
) -> None:
    """`shell_hook` asks pixi for the bash activation of an env and returns it verbatim."""
    pixi = Pixi(tmp_path)
    fp.register(
        [
            tool_paths["pixi"],
            "shell-hook",
            "-s",
            "bash",
            "-e",
            "default",
            "--manifest-path",
            str(pixi.manifest),
        ],
        stdout='export PATH="/env/bin:$PATH"\n',
    )
    assert pixi.shell_hook() == 'export PATH="/env/bin:$PATH"\n'


@pytest.mark.parametrize(
    ("call", "expected"),
    [
        (
            lambda p: p.global_install("shared", ["python>=3.11", "ripgrep"]),
            ["global", "install", "--environment", "shared", "python>=3.11", "ripgrep"],
        ),
        (
            lambda p: p.exec(("build",), ("python", "-m", "build")),
            ["exec", "--spec", "build", "python", "-m", "build"],
        ),
    ],
)
def test_pixi_builds_argv(
    call: Callable[[Pixi], object],
    expected: list[str],
    fp: FakeProcess,
    tmp_path: Path,
    tool_paths: dict[str, str],
) -> None:
    """`global_install` and `exec` render their flags into the exact pixi argv."""
    fp.register([tool_paths["pixi"], fp.any()], stdout="")
    call(Pixi(tmp_path))
    assert list(fp.calls[-1]) == [tool_paths["pixi"], *expected]


class FakeLocalMissingPixi:
    """A plumbum `local` stand-in where `pixi` is off PATH but any other name resolves."""

    def __getitem__(self, key: str) -> str:
        if key == "pixi":
            raise CommandNotFound("pixi", [])
        return key


@pytest.mark.parametrize("present", [True, False])
def test_pixi_command_resolves_from_home_or_bootstraps(
    present: bool, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Off PATH, pixi is used from `PIXI_HOME` when present, else the engine bootstraps once."""
    monkeypatch.setattr("chefe.backends.pixi.local", FakeLocalMissingPixi())
    monkeypatch.setenv("PIXI_HOME", str(tmp_path))
    binary = tmp_path / "bin" / "pixi"
    binary.parent.mkdir(parents=True)
    if present:
        binary.touch()
    installs: list[bool] = []
    monkeypatch.setattr(Pixi, "bootstrap", lambda self: installs.append(True))
    assert Pixi(tmp_path).command == str(binary)
    assert installs == ([] if present else [True])


def test_pixi_bootstrap_runs_the_official_installer(fp: FakeProcess, tmp_path: Path) -> None:
    """bootstrap shells out to pixi's official install script."""
    fp.register([fp.any()], stdout="")
    Pixi(tmp_path).bootstrap()
    assert any("pixi.sh/install.sh" in str(arg) for call in fp.calls for arg in call)


def test_pixi_activated_puts_the_env_bin_on_path(tmp_path: Path) -> None:
    """`activated` prepends the env's bin when it exists, and leaves PATH alone when it doesn't.

    This is what lets an env-installed manager (pnpm/yarn/…) resolve right after `pixi install`.
    """
    pixi = Pixi(tmp_path)
    env_bin = tmp_path / ".pixi" / "envs" / "default" / "bin"
    env_bin.mkdir(parents=True)
    with pixi.activated("default"):
        assert str(env_bin) in local.env["PATH"]
    before = local.env["PATH"]
    with Pixi(tmp_path / "empty").activated("default"):
        assert local.env["PATH"] == before


def test_global_install_spans_all_ecosystems(
    fp: FakeProcess, tmp_path: Path, tool_paths: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A global install reaches every language/toolchain: conda, then env pip/npm/cargo."""
    monkeypatch.setenv("PIXI_HOME", str(tmp_path / "pixi"))
    (tmp_path / "chefe.toml").write_text(
        '[workspace]\nname = "demo"\nplatforms = ["linux-64"]\n'
        '[deps]\nripgrep = "*"\npython = "*"\nnodejs = "*"\nrust = "*"\n'
        '[python.deps]\nruff = ">=0.6"\n'
        '[nodejs.deps]\nprettier = ">=3"\n[rust.deps]\nbat = "*"\n'
    )
    prefix = tmp_path / "pixi" / "envs" / "demo"
    for argv0 in (
        tool_paths["pixi"],
        *(str(prefix / "bin" / t) for t in ("python", "npm", "cargo")),
    ):
        fp.register([argv0, fp.any()], stdout="")
    PackageManager(tmp_path).glob.install()
    cmds = [list(c) for c in fp.calls]
    conda = next(c for c in cmds if c[0] == tool_paths["pixi"])
    assert {"python", "nodejs", "rust", "ripgrep"} <= set(conda)
    assert [str(prefix / "bin" / "python"), "-m", "pip", "install", "ruff>=0.6"] in cmds
    assert [str(prefix / "bin" / "npm"), "install", "-g", "prettier@>=3"] in cmds
    assert [str(prefix / "bin" / "cargo"), "install", "--root", str(prefix), "bat"] in cmds


@pytest.mark.parametrize(
    ("call", "match"),
    [
        (lambda p, prefix: p("install"), r"`pixi install` failed"),
        (lambda p, prefix: p.global_install("demo", ["ripgrep"]), r"`pixi global install` failed"),
        (lambda p, prefix: p.global_add("demo", ("ripgrep",)), r"`pixi global add` failed"),
        (lambda p, prefix: p.global_remove("demo", ("ripgrep",)), r"`pixi global remove` failed"),
        (lambda p, prefix: p.global_list(), r"`pixi global list` failed"),
        (lambda p, prefix: p.global_pip(prefix, ["ruff"]), "global pip install failed"),
        (lambda p, prefix: p.global_npm(prefix, ["prettier"]), "global npm install failed"),
        (lambda p, prefix: p.global_cargo(prefix, ["bat"]), "global cargo install failed"),
        (lambda p, prefix: p.bootstrap(), "pixi installer failed"),
    ],
    ids=[
        "call",
        "global-install",
        "global-add",
        "global-remove",
        "global-list",
        "global-pip",
        "global-npm",
        "global-cargo",
        "bootstrap",
    ],
)
def test_every_seam_raises_chefe_error_on_failure(
    call: Callable[[Pixi, Path], object],
    match: str,
    fp: FakeProcess,
    tool_paths: dict[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failing tool at any seam surfaces as a ChefeError instead of a green no-op: a backend
    call, each ecosystem global-install helper, and the one-time pixi bootstrap installer."""
    monkeypatch.setenv("PIXI_HOME", str(tmp_path / "pixi"))
    prefix = tmp_path / "pixi" / "envs" / "demo"
    # `global_add` first queries `global list --json` to pick add-vs-create; say the env exists
    # so the failure under test is the add itself, not the existence probe.
    fp.register(
        [tool_paths["pixi"], "global", "list", "--json"], stdout=json.dumps([{"name": "demo"}])
    )
    fp.register([tool_paths["pixi"], fp.any()], returncode=1)
    fp.register([str(local["sh"].executable), fp.any()], returncode=1)
    for binary in ("python", "npm", "cargo"):
        fp.register([str(prefix / "bin" / binary), fp.any()], returncode=1)
    with pytest.raises(ChefeError, match=match):
        call(Pixi(tmp_path), prefix)


@pytest.mark.parametrize("code", [0, 7])
def test_exec_preserves_exit_code(
    fp: FakeProcess, tool_paths: dict[str, str], tmp_path: Path, code: int
) -> None:
    """`chefe x` passes the wrapped command's exit code through."""
    fp.register([tool_paths["pixi"], fp.any()], returncode=code)
    assert Pixi(tmp_path).exec((), ("ruff", "check")) == code


def test_global_add_creates_env_when_missing(
    fp: FakeProcess, tool_paths: dict[str, str], tmp_path: Path
) -> None:
    """A conda `global_add` against a non-existent env uses `install` to create it on demand.

    `pixi global add` requires an existing `--environment`; `pixi global install` creates one,
    so chefe picks the create verb whenever `global list` shows the env is not there yet.
    """
    fp.register([tool_paths["pixi"], "global", "list", "--json"], stdout=json.dumps([]))
    fp.register([tool_paths["pixi"], fp.any()], stdout="")
    Pixi(tmp_path).global_add("life", ("ripgrep",))
    assert list(fp.calls[-1]) == [
        tool_paths["pixi"],
        "global",
        "install",
        "--environment",
        "life",
        "ripgrep",
    ]


def test_global_add_remove_and_list_build_pixi_args(
    fp: FakeProcess, tool_paths: dict[str, str], tmp_path: Path
) -> None:
    """The lightweight global helpers mirror Pixi's global subcommands."""
    # The env already exists, so `global_add` takes the plain `add` verb (not create).
    fp.register(
        [tool_paths["pixi"], "global", "list", "--json"], stdout=json.dumps([{"name": "shared"}])
    )
    for _ in range(4):
        fp.register([tool_paths["pixi"], fp.any()], stdout="")
    pixi = Pixi(tmp_path)
    pixi.global_add("shared", ("ripgrep", "fd-find"))
    pixi.global_remove("shared", ("fd-find",))
    pixi.global_list("shared", "rip", json=True, sort_by="size")
    pixi.global_list(regex="ruff")

    calls = [list(call) for call in fp.calls]
    assert [
        tool_paths["pixi"],
        "global",
        "add",
        "--environment",
        "shared",
        "ripgrep",
        "fd-find",
    ] in calls
    assert [
        tool_paths["pixi"],
        "global",
        "remove",
        "--environment",
        "shared",
        "fd-find",
    ] in calls
    assert [
        tool_paths["pixi"],
        "global",
        "list",
        "--environment",
        "shared",
        "--json",
        "--sort-by",
        "size",
        "rip",
    ] in calls
    assert [tool_paths["pixi"], "global", "list", "ruff"] in calls
