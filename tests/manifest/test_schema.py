from collections.abc import Mapping

import pytest
import tomlkit
from hypothesis import HealthCheck, given, settings
from pydantic import ValidationError

from chefe.core import platform_scopes
from chefe.manifest import Manifest, Scope, Spec

from ..support.strategies import dep_maps, manifests, specs, toolchain_names


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


def fold(manifest: Manifest, env_name: str, *, platform: str) -> dict[str, str]:
    """Oracle for declared(): the scopes active for ``env_name`` folded in order, last writer wins.

    Active means the base scope plus its covering platform overlays and, for the default env,
    `[dev]`. A named env adds itself with its own overlays, and a `no-default` env stands alone.
    """
    selectors = platform_scopes(platform)
    overlays = [scope for plat, scope in manifest.on.items() if plat in selectors]
    env = manifest.envs.get(env_name)
    if env is None:
        scopes: list[Scope] = [manifest, *overlays, manifest.dev]
    else:
        own = [env, *(scope for plat, scope in env.on.items() if plat in selectors)]
        scopes = own if env.no_default else [manifest, *overlays, *own]
    groups = [group for scope in scopes for group in scope.groups().items()]
    return {name: source for source, deps in groups for name in deps}


@given(manifests())
@settings(suppress_health_check=[HealthCheck.too_slow])
def test_declared_matches_active_scope_fold(manifest: Manifest) -> None:
    """declared() folds exactly the active scopes and nothing else.

    That is base plus its covering overlays, then the env with its own overlays, while a
    `no-default` env stands alone, so an env's exclusive dep never leaks into default.
    """
    platform = manifest.workspace.platforms[0]
    base = manifest.declared("default", platform=platform)
    default = fold(manifest, "default", platform=platform)
    assert {n: d.source for n, d in base.items()} == default
    for env_name, env in manifest.envs.items():
        scoped = manifest.declared(env_name, platform=platform)
        assert {n: d.source for n, d in scoped.items()} == fold(
            manifest, env_name, platform=platform
        )
        assert not {dep for dep in env.deps if dep not in default} & set(base)


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
    toolchains = manifest.toolchains_for("default", platform="linux-64")
    managers = {
        "nodejs": "pnpm",
        "bun": "bun",
        "deno": "deno",
        "zig": "zig",
        "c-compiler": "clang",
        "cxx-compiler": "conan",
    }
    assert {name: spec.manager for name, spec in toolchains.items()} == managers
    assert toolchains["cxx-compiler"].deps["fmt"].version == ">=11"
    assert manifest.declared("default", platform="linux-64")["fmt"].source == "cxx-compiler"


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
        (
            """
            [workspace]
            name = "toolchains"
            platforms = ["linux-64"]

            [envs.chefe-platforms]
            """,
            r"\[envs.chefe-platforms\] is reserved",
        ),
    ],
)
def test_manifest_rejects_invalid_scope_tables(*, text: str, match: str) -> None:
    """Scoped tables require matching runtime deps, and reserved env names stay reserved.

    `envs.default` reaches the same guard through `PackageManager.load`.
    """
    with pytest.raises(ValidationError, match=match):
        Manifest.from_toml(text)


@given(name=toolchain_names(), deps=dep_maps())
def test_arbitrary_toolchain_names_are_discovered_from_toml(
    name: str, deps: Mapping[str, Spec]
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
    doc[name]["deps"].update({package: spec.to_toml() for package, spec in deps.items()})

    manifest = Manifest.from_toml(tomlkit.dumps(doc))
    toolchain = manifest.toolchains_for("default", platform="linux-64")[name]
    assert toolchain.manager == name
    assert toolchain.bin_dirs == ["tools/bin"]
    assert {package: spec.version or "*" for package, spec in toolchain.deps.items()} == {
        package: spec.version or "*" for package, spec in deps.items()
    }
    for package in deps:
        assert manifest.declared("default", platform="linux-64")[package].source == name


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
    toolchain = manifest.toolchains_for("frontend", platform="linux-64")["nodejs"]
    assert toolchain.manager == "pnpm"
    assert set(toolchain.deps) == {"svelte", "typescript"}
    assert set(toolchain.dev.deps) == {"prettier", "vite"}
    assert toolchain.bin_dirs == ["custom/bin", "frontend/bin"]


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("", []),
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


@pytest.mark.parametrize("scope", ["", "envs.analysis."])
def test_free_threaded_python_runtime_owns_python_toolchain(scope: str) -> None:
    """`python-freethreading` permits normal `[python.deps]` package declarations."""
    environment = (
        """
[envs.analysis]
no-default = true

[envs.analysis.deps]
python-freethreading = "*"
"""
        if scope
        else '\n[deps]\npython-freethreading = "*"\n'
    )
    manifest = Manifest.from_toml(
        '[workspace]\nname = "w"\nplatforms = ["linux-64"]\n'
        f'{environment}\n[{scope}python.deps]\npydantic = "*"\n'
    )

    assert manifest.toolchains_for("analysis" if scope else "default", platform="linux-64")[
        "python"
    ].deps == {"pydantic": Spec(version="*")}


def test_local_python_projects_cover_every_scope_once() -> None:
    """Local project metadata from root, dev, overlays, and envs participates in locking."""
    manifest = Manifest.from_toml(
        """
        [workspace]
        name = "w"
        platforms = ["linux-64"]

        [deps]
        python = "*"

        [python.deps]
        root = { path = "packages/root", editable = true }
        registry = ">=1"

        [dev.python.deps]
        root = { path = "packages/root", editable = true }

        [on.linux.python.deps]
        overlay = { path = "packages/overlay", editable = true }

        [envs.analysis]
        no-default = true

        [envs.analysis.deps]
        python = "*"

        [envs.analysis.python.deps]
        environment = { path = "packages/environment", editable = true }

        [envs.analysis.on.linux.python.deps]
        target = { path = "packages/target", editable = true }
        """
    )

    assert manifest.local_python_projects() == [
        "packages/environment",
        "packages/overlay",
        "packages/root",
        "packages/target",
    ]


def test_standalone_manager_is_provisioned_from_manager_field() -> None:
    """A standalone manager such as pnpm, yarn, bun, or uv is auto-added to conda deps.

    The `manager` field alone is enough, while a bundled manager, a compiler-style manager, and
    an explicit pin are all left untouched.
    """
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
