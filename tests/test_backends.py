from __future__ import annotations

import json
from pathlib import Path

from pytest_subprocess import FakeProcess

from chefe.backends import Cargo, Npm, Pixi, Tool
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
    """The base backend pins nothing; subclasses (pixi/npm) override to add scope args."""
    assert Tool().scope() == ()


def test_npm_available_requires_package_json(tmp_path: Path) -> None:
    """npm refuses to run until a `package.json` exists in its prefix."""
    npm = Npm(tmp_path)
    assert npm.available() is False
    (tmp_path / "package.json").write_text("{}")
    assert npm.available() is True


def test_npm_installed_reads_node_modules(tmp_path: Path) -> None:
    """`installed` discovers both plain and scoped packages under node_modules."""
    for rel, name, version in (
        ("node_modules/prettier", "prettier", "3.2.0"),
        ("node_modules/@scope/pkg", "@scope/pkg", "1.0.0"),
    ):
        directory = tmp_path / rel
        directory.mkdir(parents=True)
        (directory / "package.json").write_text(json.dumps({"name": name, "version": version}))
    found = Npm(tmp_path).installed("default")
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


def test_npm_scope_pins_prefix_when_invoked(
    fp: FakeProcess, tmp_path: Path, tool_paths: dict[str, str]
) -> None:
    """An available npm runs with `--prefix <out> --no-audit --no-fund` after the verb."""
    (tmp_path / "package.json").write_text("{}")
    fp.register([tool_paths["npm"], fp.any()], stdout="")
    Npm(tmp_path)("install")
    assert list(fp.calls[-1]) == [
        tool_paths["npm"],
        "install",
        "--prefix",
        str(tmp_path),
        "--no-audit",
        "--no-fund",
    ]


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
