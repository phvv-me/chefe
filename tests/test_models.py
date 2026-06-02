from __future__ import annotations

import tomllib

import tomlkit
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from chefe.compiled import PackageJson, PixiManifest
from chefe.manifest import Document, Manifest, Registry, Runtime, Scope, Spec
from chefe.utils import satisfied

from .strategies import ECOSYSTEMS, dep_maps, manifests, specs


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


@given(manifests())
def test_runtime_is_ensured_per_ecosystem(manifest: Manifest) -> None:
    """A non-empty `[<eco>.deps]` forces its conda runtime into the compiled `dependencies`."""
    pixi = PixiManifest.from_manifest(manifest)
    for eco in ECOSYSTEMS:
        # pypi deps land in pypi-dependencies; their `python` runtime is ensured in [deps].
        if getattr(manifest, eco).deps:
            assert Runtime[eco].value in pixi.dependencies


@given(pin=st.sampled_from(["==3.10", ">=3.12", "*"]))
def test_user_pinned_runtime_is_preserved(pin: str) -> None:
    """A runtime the user pins in `[deps]` is never overwritten by the ensure step."""
    manifest = Manifest.model_validate(
        {
            "workspace": {"name": "w", "platforms": ["linux-64"]},
            "deps": {"python": pin},
            "pypi": {"deps": {"requests": "*"}},
        }
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
    """declared() equals folding exactly the active scopes: base, prefix-matched overlays, env."""
    platform = manifest.workspace.platforms[0]
    overlays = [s for plat, s in manifest.on.items() if platform.startswith(plat)]

    base = manifest.declared("default", platform)
    assert {n: d.source for n, d in base.items()} == fold([manifest, *overlays])

    for env_name, env in manifest.envs.items():
        scoped = manifest.declared(env_name, platform)
        assert {n: d.source for n, d in scoped.items()} == fold([manifest, *overlays, env])
        # An env's exclusive dep (not in any active default scope) is absent from default.
        for name in env.deps:
            if name not in fold([manifest, *overlays]):
                assert name not in base


def test_env_carries_nested_platform_overlay() -> None:
    """A `[envs.<name>.on.<plat>]` overlay compiles into the feature's `target` table."""
    manifest = Manifest.model_validate(
        {
            "workspace": {"name": "w", "platforms": ["linux-64"]},
            "envs": {"serving": {"on": {"linux-64": {"deps": {"cupy": ">=13"}}}}},
        }
    )
    pixi = PixiManifest.from_manifest(manifest)
    overlay = Document.dig(pixi.feature, "serving", "target", "linux-64", "dependencies")
    assert Spec.model_validate(overlay["cupy"]).version == ">=13"


def test_empty_env_overlay_emits_no_target() -> None:
    """An env overlay with no deps contributes no `target` entry to its feature."""
    manifest = Manifest.model_validate(
        {
            "workspace": {"name": "w", "platforms": ["linux-64"]},
            "envs": {"serving": {"deps": {"numpy": "*"}, "on": {"linux-64": {}}}},
        }
    )
    pixi = PixiManifest.from_manifest(manifest)
    assert Document.dig(pixi.feature, "serving", "target") == {}


def test_satisfied_tolerates_unparseable_spec() -> None:
    """An invalid specifier or version is treated as satisfied (display-only, pixi is the gate)."""
    assert satisfied("not-a-spec", "1.0.0")
    assert satisfied(">=1.0", "not-a-version")


@given(dep_maps())
def test_package_json_mirrors_npm_deps(deps: dict[str, Spec]) -> None:
    """package.json exists iff `[npm.deps]` is non-empty, and mirrors every package version."""
    manifest = Manifest.model_validate(
        {"workspace": {"name": "w", "platforms": ["linux-64"]}}
    ).model_copy(update={"npm": Registry(deps=deps)})
    package = PackageJson.from_manifest(manifest)
    if not deps:
        assert package is None
        return
    assert package is not None
    for name, spec in manifest.npm.deps.items():
        assert package.dependencies[name] == (spec.version or "*")
