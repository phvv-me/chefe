from chefe.compiled import PixiManifest
from chefe.manifest import Manifest


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
