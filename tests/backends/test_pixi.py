import json
import os
from collections.abc import Mapping
from pathlib import Path

import pytest
from plumbum import local
from plumbum.commands.processes import CommandNotFound
from pytest_mock import MockerFixture
from pytest_subprocess import FakeProcess

from chefe.backends import Pixi, PixiEngine, Process
from chefe.core import ChefeError


def test_shell_provisions_before_handing_over_the_terminal(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """`enter` provisions through the ordinary locked install, then gives the shell the tty."""
    order: list[str] = []
    mocker.patch.object(
        Pixi,
        "install",
        side_effect=lambda self, env, resolve=False: order.append(f"install -e {env}"),
        autospec=True,
    )
    mocker.patch.object(
        Process,
        "handover",
        side_effect=lambda command: order.append(" ".join(command.formulate()[1:])) or 0,
    )

    assert Pixi(tmp_path).enter("research") == 0
    assert order[0] == "install -e research"
    assert order[1] == f"shell --manifest-path {tmp_path / 'pixi.toml'} -e research"


@pytest.mark.parametrize("code", [0, 7])
def test_exit_code_threads_the_real_command_code(
    code: int, fp: FakeProcess, tmp_path: Path, tool_paths: Mapping[str, str]
) -> None:
    """`exit_code` runs the backend through its real seam and returns the command's own code."""
    fp.register([tool_paths["pixi"], fp.any()], returncode=code)
    assert Pixi(tmp_path).exit_code("run", "task") == code


def test_failed_pixi_install_reaches_the_callers_output(
    fp: FakeProcess,
    tmp_path: Path,
    tool_paths: Mapping[str, str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A Pixi failure is tee'd before chefe raises, including both native output streams."""
    Pixi(tmp_path).lock.write_text("version: 7\n")
    fp.register(
        [tool_paths["pixi"], fp.any()],
        returncode=17,
        stdout="pixi solver context\n",
        stderr="pixi solver failed\n",
    )

    with pytest.raises(ChefeError, match="pixi install"):
        Pixi(tmp_path).install("default")

    captured = capsys.readouterr()
    assert captured.out == "pixi solver context\n"
    assert captured.err == "pixi solver failed\n"


def test_successful_pixi_install_returns_cleanly(
    fp: FakeProcess, tmp_path: Path, tool_paths: Mapping[str, str]
) -> None:
    """A successful locked installation has no error epilogue."""
    pixi = Pixi(tmp_path)
    pixi.manifest.write_text('[workspace]\nplatforms = ["linux-64"]\n')
    pixi.lock.write_text("version: 7\n")
    fp.register([tool_paths["pixi"], fp.any()], stdout="environment ready\n")

    assert pixi.install("default") is None


def test_install_repairs_a_pypi_wheel_damaged_by_a_provider_transition(
    fp: FakeProcess,
    mocker: MockerFixture,
    tmp_path: Path,
    tool_paths: Mapping[str, str],
) -> None:
    """A retained wheel whose import roots vanished is reinstalled through the locked env."""
    pixi = Pixi(tmp_path)
    pixi.lock.write_text("version: 7\n")
    mocker.patch.object(
        Pixi,
        "_broken_python_packages",
        side_effect=[("cupy-cuda13x",), ()],
        autospec=True,
    )
    base = [tool_paths["pixi"], fp.any(), "--manifest-path", str(pixi.manifest), "--locked"]
    fp.register([*base, "-e", "default"], stdout="environment ready\n")
    fp.register([*base, "-e", "default", "cupy-cuda13x"], stdout="package repaired\n")

    pixi.install("default")

    assert len(fp.calls) == 2
    assert list(fp.calls[1])[1:] == [
        "reinstall",
        "--manifest-path",
        str(pixi.manifest),
        "--locked",
        "-e",
        "default",
        "cupy-cuda13x",
    ]


def test_pypi_integrity_probe_finds_missing_top_level_import_roots(tmp_path: Path) -> None:
    """The probe ignores metadata-only and Conda records but reports a damaged uv-pixi wheel."""
    pixi = Pixi(tmp_path)
    site_packages = pixi.env_prefix("default") / "lib" / "python3.14" / "site-packages"
    site_packages.mkdir(parents=True)
    for name, installer, roots in (
        ("broken-1.0.dist-info", "uv-pixi", "broken\n"),
        ("partial-1.0.dist-info", "uv-pixi", "partial\nmissing_companion\n"),
        ("editable-1.0.dist-info", "uv-pixi", "editable\n"),
        ("metadata-only-1.0.dist-info", "uv-pixi", "\n"),
        ("conda-owned-1.0.dist-info", "conda", "conda_owned\n"),
    ):
        metadata = site_packages / name
        metadata.mkdir()
        metadata.joinpath("METADATA").write_text(f"Name: {name.split('-1.0')[0]}\nVersion: 1.0\n")
        metadata.joinpath("INSTALLER").write_text(installer)
        metadata.joinpath("top_level.txt").write_text(roots)
        metadata.joinpath("RECORD").write_text("")
        if name.startswith("editable"):
            metadata.joinpath("direct_url.json").write_text('{"dir_info":{"editable":true}}')
    site_packages.joinpath("partial.py").write_text("")

    assert pixi._broken_python_packages("default") == ("broken",)


def test_native_editable_probe_finds_sources_newer_than_the_installed_extension(
    tmp_path: Path,
) -> None:
    """A changed native source makes its editable package a targeted reinstall candidate."""
    pixi = Pixi(tmp_path)
    site_packages = pixi.env_prefix("default") / "lib" / "python3.14" / "site-packages"
    metadata = site_packages / "native-demo-1.0.dist-info"
    artifact = site_packages / "native_demo" / "_native.cpython-314-x86_64-linux-gnu.so"
    source = tmp_path / "native-demo"
    metadata.mkdir(parents=True)
    artifact.parent.mkdir()
    source.mkdir()
    artifact.write_bytes(b"binary")
    source.joinpath("native.cpp").write_text("void changed() {}\n")
    metadata.joinpath("METADATA").write_text("Name: native-demo\nVersion: 1.0\n")
    metadata.joinpath("INSTALLER").write_text("uv-pixi")
    metadata.joinpath("direct_url.json").write_text(
        json.dumps({"url": source.as_uri(), "dir_info": {"editable": True}})
    )
    metadata.joinpath("RECORD").write_text(
        f"{artifact.relative_to(site_packages)},,\n"
        "native-demo-1.0.dist-info/INSTALLER,,\n"
        "native-demo-1.0.dist-info/METADATA,,\n"
        "native-demo-1.0.dist-info/RECORD,,\n"
        "native-demo-1.0.dist-info/direct_url.json,,\n"
    )
    os.utime(artifact, ns=(1_000_000_000, 1_000_000_000))
    os.utime(source / "native.cpp", ns=(2_000_000_000, 2_000_000_000))

    assert pixi._stale_native_editable_packages("default") == ("native-demo",)

    os.utime(artifact, ns=(3_000_000_000, 3_000_000_000))
    assert pixi._stale_native_editable_packages("default") == ()


def test_install_rebuilds_a_stale_native_editable(
    fp: FakeProcess,
    mocker: MockerFixture,
    tmp_path: Path,
    tool_paths: Mapping[str, str],
) -> None:
    """A stale native editable is reinstalled through the same locked environment."""
    pixi = Pixi(tmp_path)
    pixi.lock.write_text("version: 7\n")
    mocker.patch.object(Pixi, "_broken_python_packages", return_value=(), autospec=True)
    mocker.patch.object(
        Pixi,
        "_stale_native_editable_packages",
        return_value=("cutoken",),
        autospec=True,
    )
    base = [tool_paths["pixi"], fp.any(), "--manifest-path", str(pixi.manifest), "--locked"]
    fp.register([*base, "-e", "default"], stdout="environment ready\n")
    fp.register([*base, "-e", "default", "cutoken"], stdout="package rebuilt\n")

    pixi.install("default")

    assert len(fp.calls) == 2
    assert list(fp.calls[1])[1:] == [
        "reinstall",
        "--manifest-path",
        str(pixi.manifest),
        "--locked",
        "-e",
        "default",
        "cutoken",
    ]


def test_install_fails_when_a_repaired_python_package_is_still_incomplete(
    fp: FakeProcess,
    mocker: MockerFixture,
    tmp_path: Path,
    tool_paths: Mapping[str, str],
) -> None:
    """A successful reinstall cannot conceal a package that remains structurally broken."""
    pixi = Pixi(tmp_path)
    pixi.lock.write_text("version: 7\n")
    mocker.patch.object(
        Pixi,
        "_broken_python_packages",
        side_effect=[("cupy-cuda13x",), ("cupy-cuda13x",)],
        autospec=True,
    )
    base = [tool_paths["pixi"], fp.any(), "--manifest-path", str(pixi.manifest), "--locked"]
    fp.register([*base, "-e", "default"], stdout="environment ready\n")
    fp.register([*base, "-e", "default", "cupy-cuda13x"], stdout="package repaired\n")

    with pytest.raises(ChefeError, match="remain incomplete.*cupy-cuda13x"):
        pixi.install("default")


def test_install_reports_a_failed_python_package_repair(
    fp: FakeProcess,
    mocker: MockerFixture,
    tmp_path: Path,
    tool_paths: Mapping[str, str],
) -> None:
    """A failed targeted reinstall remains a hard installation failure."""
    pixi = Pixi(tmp_path)
    pixi.lock.write_text("version: 7\n")
    mocker.patch.object(
        Pixi,
        "_broken_python_packages",
        return_value=("cupy-cuda13x",),
        autospec=True,
    )
    base = [tool_paths["pixi"], fp.any(), "--manifest-path", str(pixi.manifest), "--locked"]
    fp.register([*base, "-e", "default"], stdout="environment ready\n")
    fp.register([*base, "-e", "default", "cupy-cuda13x"], returncode=9, stderr="repair failed\n")

    with pytest.raises(ChefeError, match="pixi reinstall"):
        pixi.install("default")


def test_failed_pixi_query_replays_captured_output(
    fp: FakeProcess,
    tmp_path: Path,
    tool_paths: Mapping[str, str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Captured Pixi queries replay native diagnostics before their user-facing error."""
    fp.register(
        [tool_paths["pixi"], fp.any()],
        returncode=1,
        stdout="list context\n",
        stderr="list failed\n",
    )

    with pytest.raises(ChefeError, match="pixi list"):
        Pixi(tmp_path).installed("default")

    captured = capsys.readouterr()
    assert captured.out == "list context\n"
    assert captured.err == "list failed\n"


def test_locked_environment_refuses_manifest_drift_with_actionable_error(
    fp: FakeProcess, tmp_path: Path, tool_paths: Mapping[str, str]
) -> None:
    """A stale lock aborts without a second solving call and explains the explicit escape."""
    pixi = Pixi(tmp_path)
    pixi.lock.write_text("version: 7\n")
    fp.register(
        [tool_paths["pixi"], fp.any()],
        returncode=1,
        stderr="the lock file is not up-to-date with the workspace\n",
    )

    with pytest.raises(ChefeError, match=r"chefe.toml drifted.*--resolve"):
        pixi.install("default")

    assert len(fp.calls) == 1
    assert "install" in list(fp.calls[0])
    assert "--locked" in list(fp.calls[0])


def test_editable_path_environment_installs_frozen_after_resolving(
    fp: FakeProcess, tmp_path: Path, tool_paths: Mapping[str, str]
) -> None:
    """A mutable editable source trusts the resolved lock without demanding unchanged code."""
    pixi = Pixi(tmp_path)
    pixi.manifest.write_text('[pypi-dependencies.demo]\npath = "../demo"\neditable = true\n')
    pixi.lock.write_text("version: 7\n")
    for _ in range(2):
        fp.register([tool_paths["pixi"], fp.any()], stdout="environment ready\n")

    pixi.install("default", resolve=True)

    assert "--locked" not in list(fp.calls[0])
    assert "--frozen" in list(fp.calls[1])


@pytest.mark.parametrize("resolve", [False, True])
def test_uninstalled_task_environment_uses_an_existing_lock_unless_resolve_was_requested(
    *,
    resolve: bool,
    fp: FakeProcess,
    tmp_path: Path,
    tool_paths: Mapping[str, str],
) -> None:
    """The compiled pair selects `--locked`, while `--resolve` deliberately omits it."""
    pixi = Pixi(tmp_path)
    pixi.lock.write_text("version: 7\n")
    fp.register([tool_paths["pixi"], fp.any()], stdout="")

    assert pixi.launch("run", "build", env="default", resolve=resolve) == 0
    assert all(("--locked" in list(call)) is not resolve for call in fp.calls)


def test_installed_task_environment_runs_as_is(
    fp: FakeProcess, tmp_path: Path, tool_paths: Mapping[str, str]
) -> None:
    """A completed environment is not reinstalled while concurrent tasks use it."""
    pixi = Pixi(tmp_path)
    pixi.lock.write_text("version: 7\n")
    fingerprint = pixi.env_prefix("default") / "conda-meta" / ".pixi-environment-fingerprint"
    fingerprint.parent.mkdir(parents=True)
    fingerprint.write_text("ready\n")
    fp.register([tool_paths["pixi"], fp.any()], stdout="")

    assert pixi.launch("run", "build", env="default") == 0
    assert "--as-is" in list(fp.calls[0])
    assert "--locked" not in list(fp.calls[0])


def test_install_requires_a_lock_unless_resolution_was_requested(
    fp: FakeProcess, tmp_path: Path, tool_paths: Mapping[str, str]
) -> None:
    """A missing generated lock never turns an ordinary install into an implicit solve."""
    with pytest.raises(ChefeError, match=r"pixi.lock is missing.*--resolve"):
        Pixi(tmp_path).install("serving")

    assert not fp.calls


def test_resolving_install_verifies_the_new_lock_through_the_locked_path(
    fp: FakeProcess, tmp_path: Path, tool_paths: Mapping[str, str]
) -> None:
    """A solve is successful only after the resulting pair passes Pixi's locked install check."""
    pixi = Pixi(tmp_path)
    pixi.lock.write_text("version: 7\n")
    base = [tool_paths["pixi"], "install", "--manifest-path", str(pixi.manifest)]
    fp.register([*base, "-e", "serving"], stdout="environment ready\n")
    fp.register([*base, "--locked", "-e", "serving"], stdout="lock verified\n")

    pixi.install("serving", resolve=True)

    assert len(fp.calls) == 2
    assert "--locked" not in list(fp.calls[0])
    assert "--locked" in list(fp.calls[1])


def test_locked_task_failure_keeps_its_exit_code(
    fp: FakeProcess, tmp_path: Path, tool_paths: Mapping[str, str]
) -> None:
    """A normal task failure under `--locked` is not mislabeled as manifest drift."""
    pixi = Pixi(tmp_path)
    pixi.lock.write_text("version: 7\n")
    fp.register(
        [tool_paths["pixi"], fp.any()],
        returncode=9,
        stdout="✨ Pixi task (build): command\n",
        stderr="task says lock file is not up-to-date\n",
    )

    assert pixi.launch("run", "build", env="default") == 9


def test_pixi_scope_pins_manifest_path(tmp_path: Path) -> None:
    """The pixi backend injects `--manifest-path` so every call targets the env it owns."""
    pixi = Pixi(tmp_path)
    assert pixi.manifest == tmp_path / "pixi.toml"
    assert pixi.scope() == ("--manifest-path", str(pixi.manifest))


def test_pixi_installed_parses_list_json(
    fp: FakeProcess, tmp_path: Path, tool_paths: Mapping[str, str]
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
    fp: FakeProcess, tmp_path: Path, tool_paths: Mapping[str, str]
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
    fp: FakeProcess, tmp_path: Path, tool_paths: Mapping[str, str]
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


class FakeLocalMissingPixi:
    """A plumbum `local` stand-in where `pixi` is off PATH but any other name resolves."""

    def __getitem__(self, key: str) -> str:
        if key == "pixi":
            raise CommandNotFound("pixi", [])
        return key


@pytest.mark.parametrize("present", [True, False])
def test_pixi_command_resolves_from_home_or_bootstraps(
    *, present: bool, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Off PATH, pixi is used from `PIXI_HOME` when present, else the engine bootstraps once."""
    monkeypatch.setattr("chefe.backends.pixi.engine.local", FakeLocalMissingPixi())
    monkeypatch.setenv("PIXI_HOME", str(tmp_path))
    binary = tmp_path / "bin" / "pixi"
    binary.parent.mkdir(parents=True)
    if present:
        binary.touch()
    installs: list[bool] = []
    monkeypatch.setattr(PixiEngine, "bootstrap", lambda self: installs.append(True))
    assert Pixi(tmp_path).command == str(binary)
    assert installs == ([] if present else [True])


def test_pixi_bootstrap_runs_the_official_installer(fp: FakeProcess) -> None:
    """bootstrap shells out to pixi's official install script."""
    fp.register([fp.any()], stdout="")
    PixiEngine().bootstrap()
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
