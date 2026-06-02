from __future__ import annotations

import tomllib

import pytest

from chefe.compiled import PackageJson, PixiManifest
from chefe.manifest import Manifest

# A rich manifest that touches every compiler path: conda + pypi (indexed) + npm + cargo,
# a platform overlay, a no-default env, system requirements, env vars, and a table task.
FULL = """
[workspace]
name = "demo"
version = "0.2.0"
platforms = ["osx-arm64", "linux-64"]
channels = ["conda-forge", "nvidia"]

[system]
cuda = "13.0"

[env]
LOG_LEVEL = "info"

[deps]
python = ">=3.11"
ripgrep = "*"

[pypi]
index-strategy = "unsafe-best-match"

[pypi.indexes]
pytorch = "https://download.pytorch.org/whl/cu124"

[pypi.deps]
torch = { version = ">=2.6", index = "pytorch" }
ruff = ">=0.6"

[npm.deps]
prettier = ">=3"

[cargo.deps]
ripgrep = "*"

[on.linux.deps]
cupy = ">=13"

[envs.serving]
no-default = true

[envs.serving.pypi.deps]
vllm = ">=0.6"

[tasks]
build = "python -m demo.build"
serve = { run = "python -m demo.server", depends = ["build"] }
"""

# A minimal manifest: conda only, no ecosystems, so package.json is absent.
MINIMAL = """
[workspace]
name = "tiny"
platforms = ["linux-64"]

[deps]
python = ">=3.11"
"""


@pytest.fixture(params=[FULL, MINIMAL], ids=["full", "minimal"])
def manifest(request: pytest.FixtureRequest) -> Manifest:
    return Manifest.model_validate(tomllib.loads(request.param))


def test_pixi_toml_snapshot(manifest: Manifest, snapshot) -> None:  # noqa: ANN001
    """The compiled `pixi.toml` text is pinned for representative manifests."""
    assert PixiManifest.from_manifest(manifest).to_toml() == snapshot


def test_package_json_snapshot(manifest: Manifest, snapshot) -> None:  # noqa: ANN001
    """The compiled `package.json` text (or its absence) is pinned."""
    package = PackageJson.from_manifest(manifest)
    rendered = package.to_json() if package is not None else "<none>"
    assert rendered == snapshot
