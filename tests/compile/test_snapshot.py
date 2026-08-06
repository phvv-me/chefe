import pytest
from syrupy.assertion import SnapshotAssertion

from chefe.compiled import PackageJson, PixiManifest
from chefe.manifest import Manifest

# One manifest carries every compiler path at once, because a snapshot only catches a
# cross-path regression when all of them render into the same file.
_FULL = """
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
nodejs = "*"
rust = "*"
zig = ">=0.14"
c-compiler = "*"
cxx-compiler = "*"

[python]
index-strategy = "unsafe-best-match"

[python.indexes]
pytorch = "https://download.pytorch.org/whl/cu124"

[python.deps]
torch = { version = ">=2.6", index = "pytorch" }
ruff = ">=0.6"

[nodejs.deps]
prettier = ">=3"

[rust.deps]
ripgrep = "*"

[zig]
manager = "zig"

[c-compiler]
manager = "clang"

[cxx-compiler]
manager = "conan"

[cxx-compiler.deps]
fmt = ">=11"

[on.linux.deps]
cupy = ">=13"

[envs.serving]
no-default = true
platforms = ["linux-64"]
channels = ["conda-forge/label/python_dev", "conda-forge"]

[envs.serving.system]
cuda = "12.0"

[envs.serving.deps]
python = "*"

[envs.serving.python.deps]
vllm = ">=0.6"

[tasks]
build = "python -m demo.build"
serve = { run = "python -m demo.server", depends = ["build"] }
"""


_MINIMAL = """
[workspace]
name = "tiny"
platforms = ["linux-64"]

[deps]
python = ">=3.11"
"""


@pytest.fixture(params=[_FULL, _MINIMAL], ids=["full", "minimal"])
def manifest(request: pytest.FixtureRequest) -> Manifest:
    return Manifest.from_toml(request.param)


def test_pixi_toml_snapshot(manifest: Manifest, snapshot: SnapshotAssertion) -> None:
    """The compiled `pixi.toml` text is pinned for representative manifests."""
    assert PixiManifest.from_manifest(manifest).to_toml() == snapshot


def test_package_json_snapshot(manifest: Manifest, snapshot: SnapshotAssertion) -> None:
    """The compiled `package.json` text (or its absence) is pinned."""
    package = PackageJson.from_manifest(manifest)
    rendered = package.to_json() if package is not None else "<none>"
    assert rendered == snapshot
