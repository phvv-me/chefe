import tomllib

import pytest
import tomlkit
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from chefe.compiled import PixiManifest
from chefe.manifest import Manifest, Spec
from chefe.manifest.editing import dig

from ..support.strategies import manifests


def test_python_deps_compile_to_pixi_python_path() -> None:
    """`[python.deps]` compiles to Pixi's Python package table."""
    manifest = Manifest.from_toml(
        """
        [workspace]
        name = "w"
        platforms = ["linux-64"]

        [deps]
        python = ">=3.12"

        [python.deps]
        requests = ">=2"
        """
    )
    pixi = PixiManifest.from_manifest(manifest)
    assert pixi.dependencies["python"].version == ">=3.12"
    assert pixi.pypi_dependencies["requests"].version == ">=2"


@given(pin=st.sampled_from(["==3.10", ">=3.12", "*"]))
def test_user_pinned_runtime_is_preserved(pin: str) -> None:
    """A runtime the user pins in `[deps]` is never overwritten by the ensure step."""
    manifest = Manifest.from_toml(
        f"""
        [workspace]
        name = "w"
        platforms = ["linux-64"]

        [deps]
        python = "{pin}"

        [python.deps]
        requests = "*"
        """
    )
    pixi = PixiManifest.from_manifest(manifest)
    assert pixi.dependencies["python"].model_dump() == Spec.model_validate(pin).model_dump()


@given(manifests())
@settings(suppress_health_check=[HealthCheck.too_slow])
def test_pixi_toml_is_valid_with_workspace(manifest: Manifest) -> None:
    """to_toml always reparses as TOML carrying a `[workspace]` table."""
    text = PixiManifest.from_manifest(manifest).to_toml()
    reparsed = tomllib.loads(text)
    assert "workspace" in reparsed
    assert tomlkit.parse(text)


@pytest.mark.parametrize(
    ("body", "expected_version"),
    [
        (
            """
            [envs.serving.on.linux-64.deps]
            cupy = ">=13"
            """,
            ">=13",
        ),
        (
            """
            [envs.serving.deps]
            numpy = "*"

            [envs.serving.on.linux-64]
            """,
            None,
        ),
    ],
    ids=["with-target-deps", "empty-target"],
)
def test_env_platform_overlay_target_rendering(body: str, expected_version: str | None) -> None:
    """Env platform overlays emit a Pixi target only when they contain deps."""
    manifest = Manifest.from_toml(
        f"""
        [workspace]
        name = "w"
        platforms = ["linux-64"]

        {body}
        """
    )
    pixi = PixiManifest.from_manifest(manifest)
    if expected_version is None:
        assert dig(pixi.feature, "serving", "target") == {}
        return
    overlay = dig(pixi.feature, "serving", "target", "linux-64", "dependencies")
    assert Spec.model_validate(overlay["cupy"]).version == expected_version


def test_dev_conda_and_python_become_a_pixi_dev_feature() -> None:
    """`[dev.deps]`/`[dev.python.deps]` become a dev feature for the default environment."""
    manifest = Manifest.from_toml(
        """
        [workspace]
        name = "w"
        platforms = ["linux-64"]

        [dev.deps]
        ruff = "*"
        python = "*"

        [dev.python.deps]
        pytest = ">=8"
        """
    )
    pixi = PixiManifest.from_manifest(manifest)
    dev = dig(pixi.feature, "dev")
    assert "ruff" in dig(dev, "dependencies")
    assert "python" in dig(dev, "dependencies")
    assert "pytest" in dig(dev, "pypi-dependencies")
    assert pixi.environments["default"] == {"features": ["dev"]}


def test_matching_virtual_packages_reuse_the_root_platform_variant() -> None:
    """A matching environment floor selects the root rich platform without duplication."""
    manifest = Manifest.from_toml(
        """
        [workspace]
        name = "gpu"
        platforms = ["linux-64"]

        [system]
        cuda = "13.0"

        [envs.serving]
        platforms = ["linux-64"]

        [envs.serving.system]
        cuda = "13.0"

        [envs.analysis]
        platforms = ["linux-64"]
        """
    )
    pixi = PixiManifest.from_manifest(manifest)
    assert pixi.workspace["platforms"] == [
        {"name": "linux-64-system", "platform": "linux-64", "cuda": "13.0"}
    ]
    assert pixi.feature["serving"]["platforms"] == ["linux-64-system"]
    assert pixi.feature["analysis"]["platforms"] == ["linux-64-system"]
    assert pixi.feature["chefe-platforms"]["platforms"] == ["linux-64-system"]
    assert pixi.environments["default"] == {"features": ["chefe-platforms"]}


def test_environment_virtual_packages_create_a_named_platform_variant() -> None:
    """An environment floor adds a rich variant without changing the default route."""
    manifest = Manifest.from_toml(
        """
        [workspace]
        name = "gpu"
        platforms = ["osx-arm64", "linux-64"]

        [envs.serving]
        no-default = true
        platforms = ["linux-64"]

        [envs.serving.system]
        cuda = "13.0"
        """
    )
    body = tomllib.loads(PixiManifest.from_manifest(manifest).to_toml())
    assert body["workspace"]["platforms"] == [
        "osx-arm64",
        "linux-64",
        {"name": "linux-64-serving", "platform": "linux-64", "cuda": "13.0"},
    ]
    assert body["feature"]["serving"]["platforms"] == ["linux-64-serving"]
    assert body["feature"]["chefe-platforms"]["platforms"] == [
        "osx-arm64",
        "linux-64",
    ]
    assert body["environments"]["default"] == {"features": ["chefe-platforms"]}
    assert "system-requirements" not in body


def test_activation_scripts_resolve_from_the_chefe_dir() -> None:
    """A repo-root activation script is rewritten one level up, out of `.chefe/`.

    An absolute path rides through untouched, and the generated dotenv loader runs first.
    `dotenv = false` drops the loader entirely.
    """
    body = """
        [workspace]
        name = "demo"
        platforms = ["linux-64"]
        {dotenv}

        [activation]
        scripts = ["scripts/activate.sh", "/opt/hook.sh"]

        [deps]
        python = ">=3.11"
        """
    pixi = PixiManifest.from_manifest(Manifest.from_toml(body.format(dotenv="")))
    assert pixi.activation["scripts"] == ["dotenv.sh", "../scripts/activate.sh", "/opt/hook.sh"]
    plain = PixiManifest.from_manifest(Manifest.from_toml(body.format(dotenv="dotenv = false")))
    assert plain.activation["scripts"] == ["../scripts/activate.sh", "/opt/hook.sh"]


def test_local_path_deps_resolve_from_the_chefe_dir() -> None:
    """A repo-relative editable path dep is rewritten one level up, out of `.chefe/`.

    Pixi then canonicalizes it against the repo root, while an absolute path rides through. A
    dependency literally named `path` keeps its version, because only path *sources* shift.
    """
    manifest = Manifest.from_toml(
        """
        [workspace]
        name = "demo"
        platforms = ["linux-64"]

        [deps]
        python = ">=3.11"
        path = ">=16"

        [python.deps]
        here = { path = "packages/here", editable = true }
        there = { path = "/opt/there", editable = true }
        """
    )
    pixi = PixiManifest.from_manifest(manifest)
    assert pixi.pypi_dependencies["here"].model_extra == {
        "path": "../packages/here",
        "editable": True,
    }
    assert pixi.pypi_dependencies["there"].model_extra == {"path": "/opt/there", "editable": True}
    # a conda dependency *named* `path` keeps its version string, not a rerooted source
    assert pixi.dependencies["path"].version == ">=16"


def test_task_working_directory_only_attaches_to_a_command() -> None:
    """A command task is rebased one level up, out of `.chefe/`, and a `dir` reroots that base.

    A bare command runs from the repo root and a directory'd one from that subtree. A
    command-less aggregator, one with only `depends`, carries no `cwd`, because pixi rejects a
    working directory without a command and the directory would be meaningless, so the
    aggregator compiles to `depends-on`.
    """
    pixi = PixiManifest.from_manifest(
        Manifest.from_toml(
            """
            [workspace]
            name = "demo"
            platforms = ["linux-64"]

            [deps]
            python = ">=3.11"

            [tasks]
            unit = { run = "python -m pytest", dir = "packages/here" }
            build = "python -m demo.build"
            all = { depends = ["unit", "build"] }
            """
        )
    )
    assert pixi.tasks["unit"] == {"cmd": "python -m pytest", "cwd": "../packages/here"}
    assert pixi.tasks["build"] == {"cmd": "python -m demo.build", "cwd": ".."}
    assert pixi.tasks["all"] == {"depends-on": ["unit", "build"]}


def test_named_environment_tasks_compile_into_their_feature() -> None:
    """Keep environment-owned tasks available only through their declared feature."""
    manifest = Manifest.from_toml(
        """
        [workspace]
        name = "demo"
        platforms = ["linux-64"]

        [deps]
        python = ">=3.14"

        [envs.analysis]
        no-default = true

        [envs.analysis.deps]
        python = ">=3.14"

        [envs.analysis.tasks]
        lint = { run = "ruff check .", dir = "packages/demo" }
        """
    )

    compiled = PixiManifest.from_manifest(manifest)

    assert compiled.feature["analysis"]["tasks"] == {
        "lint": {"cmd": "ruff check .", "cwd": "../packages/demo"}
    }
    assert compiled.tasks == {}
