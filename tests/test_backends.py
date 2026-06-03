from __future__ import annotations

import json
from pathlib import Path

import pytest
from plumbum.commands.processes import CommandNotFound
from pytest_subprocess import FakeProcess

from chefe.backends import Cargo, Node, Pixi, Tool
from chefe.manager import PackageManager
from chefe.utils import current_platform


def test_current_platform_shape() -> None:
    """The host platform reads as `<os>-<arch>` from the known os/arch maps."""
    osname, arch = current_platform().split("-", 1)
    assert osname in ("osx", "linux", "win")
    assert arch in ("64", "arm64", "aarch64")


def test_tool_skips_when_unavailable() -> None:
    """A backend whose `available()` is False is a silent success, running nothing."""

    class Blocked(Tool):
        name = "nonexistent-binary"

        def available(self) -> bool:
            return False

    assert Blocked()("install") is True


def test_flags_translate_kwargs_to_cli_args() -> None:
    """Booleans become bare `--flag`, values become `--flag value`, falsy ones drop, `_`→`-`."""
    assert Tool.flags(pypi=True, cargo=False, npm=None) == ("--pypi",)
    assert Tool.flags(feature="serving", env="") == ("--feature", "serving")
    assert Tool.flags(no_default=True) == ("--no-default",)


def test_tool_default_scope_is_empty() -> None:
    """The base backend pins nothing; pixi overrides scope to add `--manifest-path`."""
    assert Tool().scope() == ()


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


def test_cargo_installed_parses_crates_toml(tmp_path: Path) -> None:
    """`installed` reads versions out of the env prefix's `.crates.toml`."""
    cargo = Cargo(tmp_path, Pixi(tmp_path))
    root = cargo.root("default")
    root.mkdir(parents=True)
    (root / ".crates.toml").write_text('[v1]\n"ripgrep 14.1.0 (registry+https://x)" = ["rg"]\n')
    found = cargo.installed("default")
    assert found["ripgrep"].version == "14.1.0"
    assert cargo.installed("missing") == {}  # absent file → empty


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


def test_pixi_global_install_builds_argv(
    fp: FakeProcess, tmp_path: Path, tool_paths: dict[str, str]
) -> None:
    """`global_install` builds `global install --environment <name> <specs…>` for pixi."""
    fp.register([tool_paths["pixi"], fp.any()], stdout="")
    Pixi(tmp_path).global_install("shared", ["python>=3.11", "ripgrep"])
    assert list(fp.calls[-1]) == [
        tool_paths["pixi"],
        "global",
        "install",
        "--environment",
        "shared",
        "python>=3.11",
        "ripgrep",
    ]


def test_pixi_exec_builds_argv(
    fp: FakeProcess, tmp_path: Path, tool_paths: dict[str, str]
) -> None:
    """`exec` runs a throwaway command, threading extra packages through as `--spec`."""
    fp.register([tool_paths["pixi"], fp.any()], stdout="")
    Pixi(tmp_path).exec(("build",), ("python", "-m", "build"))
    assert list(fp.calls[-1]) == [
        tool_paths["pixi"],
        "exec",
        "--spec",
        "build",
        "python",
        "-m",
        "build",
    ]


@pytest.mark.parametrize("manager", ["npm", "pnpm", "bun", "aube"])
def test_node_runs_the_named_manager_in_the_env_dir(
    manager: str, fp: FakeProcess, tmp_path: Path, tool_paths: dict[str, str]
) -> None:
    """The JS backend invokes whatever manager it is named, targeting the env dir by cwd, no flag.

    The same call shape works for every tool, so a new package manager needs no code, only a name.
    """
    (tmp_path / "package.json").write_text("{}")
    node = Node(tmp_path, manager)
    assert node.name == manager and node.cwd() == tmp_path
    fp.register([tool_paths[manager], fp.any()], stdout="")
    node("install")
    assert list(fp.calls[-1]) == [tool_paths[manager], "install"]


def test_cargo_sync_installs_and_uninstalls(
    fp: FakeProcess, tmp_path: Path, tool_paths: dict[str, str]
) -> None:
    """sync installs declared-but-missing crates and uninstalls those no longer declared."""
    out = tmp_path
    cargo = Cargo(out, Pixi(out))
    root = cargo.root("default")
    root.mkdir(parents=True, exist_ok=True)
    # `kept` is already installed (skipped), `stale` is no longer declared (uninstalled).
    (root / ".crates.toml").write_text(
        '[v1]\n"stale 1.0.0 (x)" = ["stale"]\n"kept 2.0.0 (x)" = ["kept"]\n'
    )
    fp.keep_last_process(True)
    fp.register(
        [tool_paths["pixi"], "run", fp.any()], stdout=""
    )  # any `pixi run cargo …` succeeds

    cargo.sync("default", {"fresh": ">=2.0", "wild": "*", "kept": "2.0.0"})

    calls = [list(c) for c in fp.calls if "cargo" in c]
    assert any("uninstall" in c and "stale" in c for c in calls)
    assert any("install" in c and "fresh" in c and "--version" in c for c in calls)
    assert any("install" in c and "wild" in c and "--version" not in c for c in calls)  # `*` spec
    assert not any("install" in c and "kept" in c for c in calls)  # already present, skipped


class FakeLocalMissingPixi:
    """A plumbum `local` stand-in where `pixi` is off PATH but any other name resolves."""

    def __getitem__(self, key: str) -> str:
        if key == "pixi":
            raise CommandNotFound("pixi", [])
        return key


def test_pixi_command_falls_back_to_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Off PATH but present in PIXI_HOME (a non-login remote shell): use it, never bootstrap."""
    monkeypatch.setattr("chefe.backends.pixi.local", FakeLocalMissingPixi())
    monkeypatch.setenv("PIXI_HOME", str(tmp_path))
    binary = tmp_path / "bin" / "pixi"
    binary.parent.mkdir(parents=True)
    binary.touch()
    installs: list[bool] = []
    monkeypatch.setattr(Pixi, "bootstrap", lambda self: installs.append(True))
    assert Pixi(tmp_path).command == str(binary)
    assert installs == []  # present already, so no engine install


def test_pixi_command_bootstraps_when_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Missing on PATH and in PIXI_HOME: the backend installs the engine, then uses it."""
    monkeypatch.setattr("chefe.backends.pixi.local", FakeLocalMissingPixi())
    monkeypatch.setenv("PIXI_HOME", str(tmp_path))
    installs: list[bool] = []
    monkeypatch.setattr(Pixi, "bootstrap", lambda self: installs.append(True))
    assert Pixi(tmp_path).command == str(tmp_path / "bin" / "pixi")
    assert installs == [True]  # bootstrapped once, lazily


def test_pixi_bootstrap_runs_the_official_installer(fp: FakeProcess, tmp_path: Path) -> None:
    """bootstrap shells out to pixi's official install script."""
    fp.register([fp.any()], stdout="")
    Pixi(tmp_path).bootstrap()
    assert any("pixi.sh/install.sh" in str(arg) for call in fp.calls for arg in call)


def test_global_install_spans_all_ecosystems(
    fp: FakeProcess, tmp_path: Path, tool_paths: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A global install reaches every ecosystem: conda via pixi, then env pip/npm/cargo."""
    monkeypatch.setenv("PIXI_HOME", str(tmp_path / "pixi"))
    (tmp_path / "chefe.toml").write_text(
        '[workspace]\nname = "demo"\nplatforms = ["linux-64"]\n'
        '[deps]\nripgrep = "*"\n[pypi.deps]\nruff = ">=0.6"\n'
        '[npm.deps]\nprettier = ">=3"\n[cargo.deps]\nbat = "*"\n'
    )
    prefix = tmp_path / "pixi" / "envs" / "demo"
    for argv0 in (
        tool_paths["pixi"],
        *(str(prefix / "bin" / t) for t in ("python", "npm", "cargo")),
    ):
        fp.register([argv0, fp.any()], stdout="")
    PackageManager(tmp_path).global_install()
    cmds = [list(c) for c in fp.calls]
    conda = next(c for c in cmds if c[0] == tool_paths["pixi"])
    assert {"python", "nodejs", "rust", "ripgrep"} <= set(conda)
    assert [str(prefix / "bin" / "python"), "-m", "pip", "install", "ruff>=0.6"] in cmds
    assert [str(prefix / "bin" / "npm"), "install", "-g", "prettier@>=3"] in cmds
    assert [str(prefix / "bin" / "cargo"), "install", "--root", str(prefix), "bat"] in cmds
