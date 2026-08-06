import json
from collections.abc import Mapping

import pytest
import tomlkit
from hypothesis import given

from chefe.compiled import PackageJson, PixiManifest
from chefe.core import ChefeError
from chefe.manifest import Manifest, Spec

from ..support.strategies import dep_maps


def manifest_with_nodejs_deps(deps: Mapping[str, Spec]) -> Manifest:
    """Build a manifest from TOML with a generated `[nodejs.deps]` table."""
    doc = tomlkit.parse(
        """
        [workspace]
        name = "w"
        platforms = ["linux-64"]

        [deps]
        nodejs = "*"

        [nodejs.deps]
        """
    )
    table = doc["nodejs"]["deps"]
    for name, spec in deps.items():
        table[name] = spec.to_toml()
    return Manifest.from_toml(tomlkit.dumps(doc))


def test_nodejs_manager_is_a_free_name_defaulting_to_npm() -> None:
    """`[nodejs] manager` is any binary name and never changes the package.json."""
    default = Manifest.from_toml(
        """
        [workspace]
        name = "w"
        platforms = ["linux-64"]

        [deps]
        nodejs = "*"

        [nodejs.deps]
        svelte = ">=5"
        """
    )
    picked = Manifest.from_toml(
        """
        [workspace]
        name = "w"
        platforms = ["linux-64"]

        [deps]
        nodejs = "*"

        [nodejs]
        manager = "aube"

        [nodejs.deps]
        svelte = ">=5"
        """
    )
    # A manager chefe has never heard of still has to validate, since the driver only decides
    # who installs from the npm registry and never what the compiled file says.
    assert default.toolchains()["nodejs"].manager is None
    assert picked.toolchains()["nodejs"].manager == "aube"
    default_pkg, picked_pkg = PackageJson.from_manifest(default), PackageJson.from_manifest(picked)
    assert default_pkg is not None and picked_pkg is not None
    assert default_pkg.to_json() == picked_pkg.to_json()


@pytest.mark.parametrize(
    ("workspace_name", "node_options", "dev_deps", "expected_name", "expected_dev"),
    [
        (
            "app",
            """
            [nodejs]
            app = true
            """,
            """
            [nodejs.dev.deps]
            vite = ">=8"
            """,
            "app",
            {"vite": ">=8"},
        ),
        ("w", "", "", "w-npm", None),
    ],
    ids=["with-dev-deps", "without-dev-deps"],
)
def test_nodejs_dev_dependencies_are_optional(
    *,
    workspace_name: str,
    node_options: str,
    dev_deps: str,
    expected_name: str,
    expected_dev: dict[str, str] | None,
) -> None:
    """`[nodejs.dev.deps]` compile to devDependencies only when present."""
    manifest = Manifest.from_toml(
        f"""
        [workspace]
        name = "{workspace_name}"
        platforms = ["linux-64"]

        [deps]
        nodejs = "*"

        {node_options}

        [nodejs.deps]
        svelte = ">=5"

        {dev_deps}
        """
    )
    package = PackageJson.from_manifest(manifest)
    assert package is not None
    data = json.loads(package.to_json())
    assert data["name"] == expected_name
    assert data["dependencies"] == {"svelte": ">=5"}
    if expected_dev is None:
        assert "devDependencies" not in data
    else:
        assert data["devDependencies"] == expected_dev
    assert "nodejs" in PixiManifest.from_manifest(manifest).dependencies


@given(dep_maps())
def test_package_json_mirrors_nodejs_deps(deps: dict[str, Spec]) -> None:
    """package.json exists iff `[nodejs.deps]` is non-empty, and it mirrors every version.

    A spec npm cannot express, such as index, path, git, or url, fails fast instead of degrading
    to `*`.
    """
    manifest = manifest_with_nodejs_deps(deps)
    if any(spec.index or spec.model_extra for spec in deps.values()):
        with pytest.raises(ChefeError, match="cannot express"):
            PackageJson.from_manifest(manifest)
        return
    package = PackageJson.from_manifest(manifest)
    assert (package is None) == (not deps)
    if package is not None:
        declared = manifest.toolchains()["nodejs"].deps
        assert all(package.dependencies[n] == (s.version or "*") for n, s in declared.items())


def test_app_package_json_takes_workspace_name_and_passthrough() -> None:
    """An app package.json uses the workspace name and merges `[nodejs.package]` verbatim."""
    manifest = Manifest.from_toml(
        """
        [workspace]
        name = "site"
        platforms = ["linux-64"]

        [deps]
        nodejs = "*"

        [nodejs]
        app = true

        [nodejs.deps]
        svelte = ">=5"

        [nodejs.package]
        type = "module"

        [nodejs.package.pnpm]
        onlyBuiltDependencies = ["esbuild"]
        """
    )
    package = PackageJson.from_manifest(manifest)
    assert package is not None
    data = json.loads(package.to_json())
    # The `-npm` suffix belongs to the pixi feature name alone, since npm resolves a
    # package by exactly the name written here.
    assert data["name"] == "site"
    assert data["type"] == "module"
    assert data["pnpm"]["onlyBuiltDependencies"] == ["esbuild"]
    assert data["dependencies"] == {"svelte": ">=5"}
