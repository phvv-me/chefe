import json
from collections.abc import Callable, Mapping
from pathlib import Path

import pytest
from plumbum import local
from pytest_subprocess import FakeProcess

from chefe.backends import Pixi, PixiEngine, PixiGlobal
from chefe.core import ChefeError
from chefe.manager import PackageManager

from ..support.workspaces import ecosystem_workspace


@pytest.mark.parametrize(
    ("call", "expected"),
    [
        (
            lambda: PixiGlobal().install("shared", ["python>=3.11", "ripgrep"]),
            ["global", "install", "--environment", "shared", "python>=3.11", "ripgrep"],
        ),
        (
            lambda: PixiEngine().exec(("build",), ("python", "-m", "build")),
            ["exec", "--spec", "build", "python", "-m", "build"],
        ),
    ],
)
def test_pixi_builds_argv(
    call: Callable[[], object],
    expected: list[str],
    fp: FakeProcess,
    tool_paths: Mapping[str, str],
) -> None:
    """The global install and `exec` render their flags into the exact pixi argv."""
    fp.register([tool_paths["pixi"], fp.any()], stdout="")
    call()
    assert list(fp.calls[-1]) == [tool_paths["pixi"], *expected]


def test_global_install_spans_all_ecosystems(
    fp: FakeProcess, tmp_path: Path, tool_paths: Mapping[str, str]
) -> None:
    """A global install reaches every language/toolchain: conda, then env pip/npm/cargo."""
    prefix = ecosystem_workspace(tmp_path, fp, tool_paths["pixi"])
    PackageManager(root=tmp_path).glob.install()
    cmds = [list(c) for c in fp.calls]
    conda = next(c for c in cmds if c[0] == tool_paths["pixi"])
    adapters = [
        [str(prefix / "bin" / "python"), "-m", "pip", "install", "ruff>=0.6"],
        [str(prefix / "bin" / "npm"), "install", "-g", "prettier@>=3"],
        [str(prefix / "bin" / "cargo"), "install", "--root", str(prefix), "bat"],
    ]
    assert {"python", "nodejs", "rust", "ripgrep"} <= set(conda)
    # Conda provides all three runtimes, so it runs before them, and the second stages then run
    # in their declared dependency order rather than merely all running.
    assert [cmd for cmd in cmds if cmd in adapters] == adapters
    assert cmds.index(conda) < cmds.index(adapters[0])


@pytest.mark.parametrize(
    ("call", "match"),
    [
        (lambda p, g, prefix: p("install"), r"`pixi install` failed"),
        (lambda p, g, prefix: g.install("demo", ["ripgrep"]), r"`pixi global install` failed"),
        (lambda p, g, prefix: g.add("demo", ("ripgrep",)), r"`pixi global add` failed"),
        (lambda p, g, prefix: g.remove("demo", ("ripgrep",)), r"`pixi global remove` failed"),
        (lambda p, g, prefix: g.show(), r"`pixi global list` failed"),
        (lambda p, g, prefix: g.pip(prefix, ["ruff"]), "global pip install failed"),
        (lambda p, g, prefix: g.npm(prefix, ["prettier"]), "global npm install failed"),
        (lambda p, g, prefix: g.cargo(prefix, ["bat"]), "global cargo install failed"),
        (lambda p, g, prefix: PixiEngine().bootstrap(), "pixi installer failed"),
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
    call: Callable[[Pixi, PixiGlobal, Path], object],
    match: str,
    fp: FakeProcess,
    tool_paths: Mapping[str, str],
    tmp_path: Path,
) -> None:
    """A failing tool at any seam surfaces as a ChefeError instead of a green no-op.

    The seams are a backend call, each ecosystem global-install helper, and the one-time pixi
    bootstrap installer.
    """
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
        call(Pixi(tmp_path), PixiGlobal(), prefix)


@pytest.mark.parametrize("code", [0, 7])
def test_exec_preserves_exit_code(
    fp: FakeProcess, tool_paths: Mapping[str, str], code: int
) -> None:
    """`chefe x` passes the wrapped command's exit code through."""
    fp.register([tool_paths["pixi"], fp.any()], returncode=code)
    assert PixiEngine().exec((), ("ruff", "check")) == code


def test_global_add_creates_env_when_missing(
    fp: FakeProcess, tool_paths: Mapping[str, str]
) -> None:
    """A conda global add against a non-existent env uses `install` to create it on demand.

    `pixi global add` requires an existing `--environment`; `pixi global install` creates one,
    so chefe picks the create verb whenever `global list` shows the env is not there yet.
    """
    fp.register([tool_paths["pixi"], "global", "list", "--json"], stdout=json.dumps([]))
    fp.register([tool_paths["pixi"], fp.any()], stdout="")
    PixiGlobal().add("life", ("ripgrep",))
    assert list(fp.calls[-1]) == [
        tool_paths["pixi"],
        "global",
        "install",
        "--environment",
        "life",
        "ripgrep",
    ]


def test_global_add_remove_and_list_build_pixi_args(
    fp: FakeProcess, tool_paths: Mapping[str, str]
) -> None:
    """The lightweight global helpers mirror Pixi's global subcommands."""
    glob, binary = PixiGlobal(), tool_paths["pixi"]
    # The env already exists, so `add` takes the plain `add` verb (not create).
    fp.register([binary, "global", "list", "--json"], stdout=json.dumps([{"name": "shared"}]))
    for _ in range(4):
        fp.register([binary, fp.any()], stdout="")
    glob.add("shared", ("ripgrep", "fd-find"))
    glob.remove("shared", ("fd-find",))
    glob.show("shared", regex="rip", json=True, sort_by="size")
    glob.show(regex="ruff")

    argv = [
        [binary, "global", "add", "--environment", "shared", "ripgrep", "fd-find"],
        [binary, "global", "remove", "--environment", "shared", "fd-find"],
        # fmt: off
        [
            binary,
            "global",
            "list",
            "--environment",
            "shared",
            "--json",
            "--sort-by",
            "size",
            "rip",
        ],
        # fmt: on
        [binary, "global", "list", "ruff"],
    ]
    assert all(expected in [list(call) for call in fp.calls] for expected in argv)
