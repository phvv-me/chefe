import json
import tomllib
from pathlib import Path

import pytest
import tomlkit
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from chefe.compiled import PackageJson, PixiManifest
from chefe.errors import ChefeError
from chefe.manifest import Document, Manifest, Scope, Spec
from chefe.utils import platform_scopes

from .strategies import dep_maps, manifests, specs, toolchain_names


def manifest_with_nodejs_deps(deps: dict[str, Spec]) -> Manifest:
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


@given(specs())
def test_spec_roundtrip_is_stable(spec: Spec) -> None:
    """Spec → to_toml → re-validate is a fixed point, and bare versions stay strings."""
    rendered = spec.model_dump()
    assert Spec.model_validate(rendered).model_dump() == rendered
    if spec.index is None and not (spec.model_extra or {}):
        assert isinstance(rendered, str)
    else:
        assert isinstance(rendered, dict) and rendered


@given(manifests())
@settings(suppress_health_check=[HealthCheck.too_slow])
def test_manifest_validation_is_idempotent(manifest: Manifest) -> None:
    """A valid manifest → dump → validate → dump is stable."""
    dumped = manifest.model_dump(by_alias=True)
    assert Manifest.model_validate(dumped).model_dump(by_alias=True) == dumped


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
    assert tomlkit.parse(text)  # comment-preserving parser agrees it is well formed


def fold(scopes: list[Scope]) -> dict[str, str]:
    """Oracle for declared(): each active scope's groups folded in order, last writer wins."""
    return {
        name: source
        for scope in scopes
        for source, deps in scope.groups().items()
        for name in deps
    }


@given(manifests())
@settings(suppress_health_check=[HealthCheck.too_slow])
def test_declared_matches_active_scope_fold(manifest: Manifest) -> None:
    """declared() folds exactly the active scopes: base plus covering overlays, then the env
    with its own overlays; a `no-default` env stands alone."""
    platform = manifest.workspace.platforms[0]
    selectors = platform_scopes(platform)
    overlays = [s for plat, s in manifest.on.items() if plat in selectors]

    base = manifest.declared("default", platform)
    assert {n: d.source for n, d in base.items()} == fold([manifest, *overlays, manifest.dev])

    for env_name, env in manifest.envs.items():
        scoped = manifest.declared(env_name, platform)
        env_overlays = [s for plat, s in env.on.items() if plat in selectors]
        active = [env, *env_overlays]
        if not env.no_default:
            active = [manifest, *overlays, *active]
        assert {n: d.source for n, d in scoped.items()} == fold(active)
        # An env's exclusive dep (not in any active default scope) is absent from default.
        for name in env.deps:
            if name not in fold([manifest, *overlays, manifest.dev]):
                assert name not in base


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
        assert Document.dig(pixi.feature, "serving", "target") == {}
        return
    overlay = Document.dig(pixi.feature, "serving", "target", "linux-64", "dependencies")
    assert Spec.model_validate(overlay["cupy"]).version == expected_version


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
    assert default.toolchains()["nodejs"].manager is None  # the backend defaults to npm
    assert picked.toolchains()["nodejs"].manager == "aube"  # any name chefe never coded
    # the npm registry is the same whichever driver installs it, so the compiled file matches
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


def test_runtime_keyed_toolchains_are_discovered_from_deps() -> None:
    """Any `[deps]` package can have a matching toolchain table."""
    manifest = Manifest.from_toml(
        """
        [workspace]
        name = "toolchains"
        platforms = ["linux-64"]

        [deps]
        nodejs = ">=25"
        bun = ">=1"
        deno = ">=2"
        zig = ">=0.14"
        c-compiler = "*"
        cxx-compiler = "*"

        [nodejs]
        manager = "pnpm"

        [nodejs.dev.deps]
        prettier = ">=3"

        [bun]
        manager = "bun"

        [deno]
        manager = "deno"

        [zig]
        manager = "zig"

        [c-compiler]
        manager = "clang"

        [cxx-compiler]
        manager = "conan"

        [cxx-compiler.deps]
        fmt = ">=11"
        """
    )
    toolchains = manifest.toolchains_for("default", "linux-64")
    assert set(toolchains) == {"nodejs", "bun", "deno", "zig", "c-compiler", "cxx-compiler"}
    assert toolchains["nodejs"].manager == "pnpm"
    assert toolchains["bun"].manager == "bun"
    assert toolchains["deno"].manager == "deno"
    assert toolchains["zig"].manager == "zig"
    assert toolchains["c-compiler"].manager == "clang"
    assert toolchains["cxx-compiler"].deps["fmt"].version == ">=11"
    declared = manifest.declared("default", "linux-64")
    assert declared["fmt"].source == "cxx-compiler"


@pytest.mark.parametrize(
    ("text", "match"),
    [
        (
            """
            [workspace]
            name = "toolchains"
            platforms = ["linux-64"]

            [zig.deps]
            zls = "*"
            """,
            r"\[zig\] has no matching package in \[deps\]",
        ),
        (
            """
            [workspace]
            name = "toolchains"
            platforms = ["linux-64"]

            [envs.frontend.nodejs.deps]
            vite = ">=8"
            """,
            r"\[envs.frontend.nodejs\] has no matching package in \[deps\]",
        ),
        (
            """
            [workspace]
            name = "toolchains"
            platforms = ["linux-64"]

            [pypi.deps]
            django = "*"
            """,
            r"\[pypi\] has no matching package in \[deps\]",
        ),
        (
            """
            [workspace]
            name = "envs"
            platforms = ["linux-64"]

            [envs.dev.deps]
            ruff = "*"
            """,
            r"\[envs.dev\] is reserved",
        ),
    ],
)
def test_manifest_rejects_invalid_scope_tables(text: str, match: str) -> None:
    """Scoped tables require matching runtime deps, and the reserved env names stay reserved
    (`envs.default` reaches the same guard through `PackageManager.load`)."""
    with pytest.raises(ValidationError, match=match):
        Manifest.from_toml(text)


@given(name=toolchain_names(), deps=dep_maps())
def test_arbitrary_toolchain_names_are_discovered_from_toml(
    name: str, deps: dict[str, Spec]
) -> None:
    """A matching `[deps]` key and table is enough; no language catalog is consulted."""
    doc = tomlkit.parse(
        f"""
        [workspace]
        name = "toolchains"
        platforms = ["linux-64"]

        [deps]
        {name} = "*"

        [{name}]
        manager = "{name}"
        bin_dirs = ["tools/bin"]

        [{name}.deps]
        """
    )
    table = doc[name]["deps"]
    for package, spec in deps.items():
        table[package] = spec.to_toml()

    manifest = Manifest.from_toml(tomlkit.dumps(doc))
    toolchain = manifest.toolchains_for("default", "linux-64")[name]
    assert toolchain.manager == name
    assert toolchain.bin_dirs == ["tools/bin"]
    assert {package: spec.version or "*" for package, spec in toolchain.deps.items()} == {
        package: spec.version or "*" for package, spec in deps.items()
    }
    for package in deps:
        assert manifest.declared("default", "linux-64")[package].source == name


def test_toolchain_specs_merge_across_named_envs() -> None:
    """Named env toolchain tables overlay the base runtime-keyed table."""
    manifest = Manifest.from_toml(
        """
        [workspace]
        name = "toolchains"
        platforms = ["linux-64"]

        [deps]
        nodejs = ">=25"

        [nodejs]
        manager = "npm"
        bin_dirs = ["custom/bin"]

        [nodejs.deps]
        svelte = ">=5"

        [nodejs.dev.deps]
        prettier = ">=3"

        [envs.frontend.deps]
        nodejs = ">=25"

        [envs.frontend.nodejs]
        manager = "pnpm"
        bin_dirs = ["frontend/bin"]

        [envs.frontend.nodejs.deps]
        typescript = ">=6"

        [envs.frontend.nodejs.dev.deps]
        vite = ">=8"
        """
    )
    toolchain = manifest.toolchains_for("frontend", "linux-64")["nodejs"]
    assert toolchain.manager == "pnpm"
    assert set(toolchain.deps) == {"svelte", "typescript"}
    assert set(toolchain.dev.deps) == {"prettier", "vite"}
    assert toolchain.bin_dirs == ["custom/bin", "frontend/bin"]


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
    dev = Document.dig(pixi.feature, "dev")
    assert "ruff" in Document.dig(dev, "dependencies")
    assert "python" in Document.dig(dev, "dependencies")
    assert "pytest" in Document.dig(dev, "pypi-dependencies")
    assert pixi.environments["default"] == {"features": ["dev"]}


@given(dep_maps())
def test_package_json_mirrors_nodejs_deps(deps: dict[str, Spec]) -> None:
    """package.json exists iff `[nodejs.deps]` is non-empty and mirrors every version; a spec
    npm cannot express (index, path, git, url) fails fast instead of degrading to `*`."""
    manifest = manifest_with_nodejs_deps(deps)
    if any(spec.index or spec.model_extra for spec in deps.values()):
        with pytest.raises(ChefeError, match="cannot express"):
            PackageJson.from_manifest(manifest)
        return
    package = PackageJson.from_manifest(manifest)
    if not deps:
        assert package is None
        return
    assert package is not None
    for name, spec in manifest.toolchains()["nodejs"].deps.items():
        assert package.dependencies[name] == (spec.version or "*")


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
    assert data["name"] == "site"  # the workspace name, no `-npm` suffix
    assert data["type"] == "module"  # framework fields ride through untouched
    assert data["pnpm"]["onlyBuiltDependencies"] == ["esbuild"]
    assert data["dependencies"] == {"svelte": ">=5"}


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        # No `[modules]` table: nothing to load (the host, e.g. gold, loads none).
        ("", []),
        # `name = "version"` pairs become ordered `name/version` specs, no discovery.
        ('\n[modules]\nnvidia = "26.3"\ngcc = "15.2.0"\n', ["nvidia/26.3", "gcc/15.2.0"]),
    ],
    ids=["empty", "ordered-pairs"],
)
def test_modules_render_ordered_specs(body: str, expected: list[str]) -> None:
    """`[modules]` renders ordered `name/version` specs, and is empty when the table is absent."""
    manifest = Manifest.from_toml(f'[workspace]\nname = "w"\n{body}')
    assert manifest.modules.specs() == expected


def test_unknown_table_error_points_to_a_chefe_upgrade() -> None:
    """An unrecognized table (usually a newer-chefe feature) names the running chefe + upgrade.

    This is the failure that motivated the message: an old chefe met a manifest using a newer
    table and previously reported only a cryptic low-level error instead of "upgrade chefe".
    """
    with pytest.raises(ValidationError, match="pip install -U chefe") as caught:
        Manifest.from_toml(
            '[workspace]\nname = "w"\nplatforms = ["x"]\n\n[future.deps]\na = "*"\n'
        )
    message = str(caught.value)
    assert "no matching package in [deps]" in message  # the cause, self-contained
    assert "0.0.test" in message  # names the running version, so the user knows to upgrade


def test_pyproject_version_matches_changelog_head() -> None:
    """The packaged version and the top changelog entry agree, so neither drifts unseen.

    Releases are cut from `pyproject.toml`, and `chefe --version` plus the upgrade hints in
    error messages read from that same metadata. A changelog that ran ahead of `pyproject`
    (as 0.0.21 once did) is exactly the silent drift this guards against.
    """
    root = Path(__file__).resolve().parent.parent
    packaged = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    headings = [
        line.removeprefix("## ").strip()
        for line in (root / "CHANGELOG.md").read_text().splitlines()
        if line.startswith("## ")
    ]
    assert headings[0] == packaged


def test_standalone_manager_is_provisioned_from_manager_field() -> None:
    """A standalone manager (pnpm/yarn/bun/uv) is auto-added to conda deps from `manager` alone;
    a bundled manager, a compiler-style manager, and an explicit pin are all left untouched."""
    pnpm = Scope.model_validate({"deps": {"nodejs": "*"}, "nodejs": {"manager": "pnpm"}})
    assert pnpm.tables({})["dependencies"] == {"nodejs": "*", "pnpm": "*"}

    npm = Scope.model_validate({"deps": {"nodejs": "*"}, "nodejs": {"manager": "npm"}})
    assert npm.tables({})["dependencies"] == {"nodejs": "*"}

    pinned = Scope.model_validate(
        {"deps": {"nodejs": "*", "pnpm": ">=10"}, "nodejs": {"manager": "pnpm"}}
    )
    assert pinned.tables({})["dependencies"] == {"nodejs": "*", "pnpm": ">=10"}

    compiler = Scope.model_validate({"deps": {"zig": "*"}, "zig": {"manager": "zig"}})
    assert compiler.tables({})["dependencies"] == {"zig": "*"}
