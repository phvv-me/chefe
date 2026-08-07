from collections.abc import Sequence
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from chefe.backends import Cargo, Pixi, Tool
from chefe.core import Installed
from chefe.manifest import Spec


def test_cargo_installed_parses_crates_toml(tmp_path: Path) -> None:
    """`installed` reads versions from `.crates.toml`, and an absent file yields nothing."""
    cargo = Cargo(Pixi(tmp_path))
    root = cargo.root("default")
    root.mkdir(parents=True)
    (root / ".crates.toml").write_text('[v1]\n"ripgrep 14.1.0 (registry+https://x)" = ["rg"]\n')
    found = cargo.installed("default")
    assert found["ripgrep"].version == "14.1.0"
    assert cargo.installed("missing") == {}


def test_cargo_installed_skips_malformed_crate_keys(tmp_path: Path) -> None:
    """A `.crates.toml` key missing its version is skipped, not crashed on.

    A well-formed key reads `"name version (source)"`; a stray single-token key used to index
    past the split's end and raise `IndexError`, taking down `chefe tree` and `chefe install`
    on an otherwise healthy env. The malformed entry is now dropped and the good one survives.
    """
    cargo = Cargo(Pixi(tmp_path))
    root = cargo.root("default")
    root.mkdir(parents=True)
    (root / ".crates.toml").write_text(
        '[v1]\n"ripgrep 14.1.0 (registry+https://x)" = ["rg"]\n"orphan" = ["x"]\n'
    )
    found = cargo.installed("default")
    assert found == {"ripgrep": Installed(version="14.1.0", kind="cargo")}


def test_cargo_sync_reconciles_declared_against_installed(
    mocker: MockerFixture, cargo: Cargo, pixi_calls: Sequence[tuple[str, ...]]
) -> None:
    """sync makes the env's crates match the declaration through `pixi run cargo`.

    Pinned to the synced env, it uninstalls crates no longer declared, installs
    declared-but-missing ones (with `--version` only for a real pin), reinstalls a drifted crate
    with `--force`, and skips a satisfied one. Each call carries `--environment <env>` so an
    env-scoped rust resolves.
    """
    mocker.patch.object(
        Cargo,
        "installed",
        return_value={
            "stale": Installed(version="1.0.0", kind="cargo"),
            "drift": Installed(version="0.1.0", kind="cargo"),
            "kept": Installed(version="2.0.0", kind="cargo"),
        },
        autospec=True,
    )
    declared = {
        "fresh": Spec.model_validate(">=2.0"),
        "wild": Spec.model_validate("*"),
        "drift": Spec.model_validate(">=0.2"),
        "kept": Spec.model_validate("2.0.0"),
        "pinned": Spec.model_validate({"version": ">=0.1", "locked": True}),
    }
    cargo.sync("serving", declared)
    prefix = str(cargo.root("serving"))
    reconciled = {
        ("cargo", "uninstall", "--root", prefix, "stale"),
        ("cargo", "install", "--root", prefix, "--version", ">=2.0", "fresh"),
        # cargo rejects `--version *`, so a wildcard spec must reach it as a bare crate name.
        ("cargo", "install", "--root", prefix, "wild"),
        ("cargo", "install", "--root", prefix, "--version", ">=0.2", "--force", "drift"),
        ("cargo", "install", "--root", prefix, "--version", ">=0.1", "--locked", "pinned"),
    }
    assert all(call[:3] == ("run", "--environment", "serving") for call in pixi_calls)
    bodies = {call[3:] for call in pixi_calls}
    assert reconciled <= bodies
    assert not any("kept" in body for body in bodies)


def test_cargo_update_refreshes_even_satisfied_crates(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """update forces retained crates through Cargo so compatible releases are not skipped."""
    pixi = Pixi(tmp_path)
    cargo = Cargo(pixi)
    mocker.patch.object(
        Cargo,
        "installed",
        return_value={"ripgrep": Installed(version="14.0.0", kind="cargo")},
        autospec=True,
    )
    calls: list[tuple[str, ...]] = []
    mocker.patch.object(
        Pixi,
        "__call__",
        side_effect=lambda self, verb, *args, **flags: calls.append(
            (verb, *Tool.flags(**flags), *args)
        ),
        autospec=True,
    )

    cargo.update("default", {"ripgrep": Spec.model_validate("<15")})

    assert "--force" in calls[0]
    assert "--version" in calls[0]
    assert "<15" in calls[0]


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        (
            {"git": "https://x/r", "branch": "main"},
            ["--git", "https://x/r", "--branch", "main"],
        ),
        (
            {"version": ">=1", "path": "../crate"},
            ["--version", ">=1", "--path", "../crate"],
        ),
        (
            {"git": "https://x/r", "tag": "v1", "rev": "abc", "locked": True},
            ["--git", "https://x/r", "--tag", "v1", "--rev", "abc", "--locked"],
        ),
    ],
    ids=["git-branch", "version-path", "git-tag-rev-locked"],
)
def test_cargo_install_args_threads_source_overrides(
    spec: dict[str, object], expected: Sequence[str]
) -> None:
    """A crate's `git`/`path`/`branch`/`tag`/`rev`/`locked` ride through as their cargo flags.

    A source-pinned crate therefore installs exactly as declared instead of from the registry.
    """
    assert Cargo.install_args(Spec.model_validate(spec)) == expected
