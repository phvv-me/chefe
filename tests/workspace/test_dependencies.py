from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import NamedTuple

import pytest

from chefe.core import ChefeError
from chefe.manager import PackageManager
from chefe.workspace import DependencyCommands

Workspace = Callable[[str], PackageManager]


def test_add_toolchain_dep_edits_manifest_and_provisions(
    workspace: Workspace, recording_backends: Sequence[tuple[str, ...]]
) -> None:
    """A non-pixi language writes `[<language>.deps]`, then installs the crate right away."""
    manager = workspace(
        """
        [deps]
        python = "*"
        rust = "*"
        """
    )
    manager.dependencies.add("ripgrep", language="rust", spec=">=14")
    text = manager.workspace.manifest.read_text()
    assert "[rust.deps]" in text
    assert 'rust = "*"' in text
    assert manager.workspace.load().toolchains()["rust"].deps["ripgrep"].version == ">=14"
    verbs = [(c[0], c[1]) for c in recording_backends]
    assert ("Pixi", "add") not in verbs
    assert ("Cargo", "sync") in verbs


def test_add_nodejs_dep_is_runnable_immediately(
    workspace: Workspace, recording_backends: Sequence[tuple[str, ...]]
) -> None:
    """`chefe add -l nodejs` runs the node install itself.

    `chefe run <bin>` then works without a separate `chefe install`, where the manifest-only add
    left the package uninstalled.
    """
    manager = workspace(
        """
        [deps]
        nodejs = "*"
        """
    )
    manager.dependencies.add("@openai/codex", language="nodejs")
    assert manager.workspace.load().toolchains()["nodejs"].deps["@openai/codex"].version == "*"
    assert ("Node", "install") in [(c[0], c[1]) for c in recording_backends]


@pytest.mark.parametrize(
    ("added", "expected"),
    [
        ({"language": "conda", "spec": "*"}, ("Pixi", "add", "requests")),
        ({"language": "python", "spec": ">=2"}, ("Pixi", "add", "--pypi", "requests>=2")),
    ],
    ids=["conda", "python"],
)
def test_add_pixi_languages_go_through_pixi_and_pull(
    *,
    workspace: Workspace,
    recording_backends: Sequence[tuple[str, ...]],
    pulled: list[bool],
    added: Mapping[str, str],
    expected: tuple[str, ...],
) -> None:
    """Conda and Python adds go through pixi, then pull resolved versions back."""
    manager = workspace(
        """
        [deps]
        python = "*"
        """
    )
    manager.dependencies.add("requests", **added)
    assert expected in recording_backends
    assert pulled == [True]


@pytest.mark.parametrize("language", ["python", "python-freethreading"])
def test_add_python_dep_accepts_the_free_threaded_runtime(
    workspace: Workspace,
    recording_backends: Sequence[tuple[str, ...]],
    monkeypatch: pytest.MonkeyPatch,
    language: str,
) -> None:
    """Both Python spellings route a free-threaded runtime to the normal Python package table."""
    monkeypatch.setattr(DependencyCommands, "pull", lambda self: None)
    manager = workspace(
        """
        [deps]
        python-freethreading = "*"
        """
    )

    manager.dependencies.add("packaging", language=language)

    assert ("Pixi", "add", "--pypi", "packaging") in recording_backends
    assert "[python-freethreading.deps]" not in manager.workspace.manifest.read_text()


class AddFailure(NamedTuple):
    """One rejected `chefe add`: the manifest it runs against, its argv, and what it must say."""

    body: str
    packages: tuple[str, ...]
    language: str
    env: str
    match: str
    absent: str = ""


_DECLARES_PYTHON = """
    [deps]
    python = "*"
    """
_ADD_FAILURES = [
    AddFailure(
        body=_DECLARES_PYTHON,
        packages=("ripgrep",),
        language="rust",
        env="",
        match=r"Language `rust` is not declared in \[deps\]",
        absent="[rust.deps]",
    ),
    AddFailure(
        body=_DECLARES_PYTHON,
        packages=("requests",),
        language="pypi",
        env="",
        match=r"Language `pypi` is not declared in \[deps\]",
    ),
    AddFailure(
        body=_DECLARES_PYTHON,
        packages=("requests",),
        language="",
        env="",
        match=r"Language `` is not declared in \[deps\]",
    ),
    AddFailure(
        body=_DECLARES_PYTHON,
        packages=(),
        language="conda",
        env="",
        match="No packages given",
    ),
    AddFailure(
        body=_DECLARES_PYTHON,
        packages=("prettier",),
        language="nodejs",
        env="frontend",
        match=r"Environment `frontend` does not exist.*\[envs.frontend.deps\]",
    ),
    AddFailure(
        body=_DECLARES_PYTHON + '\n[envs.frontend.deps]\npython = "*"\n',
        packages=("prettier",),
        language="nodejs",
        env="frontend",
        match=r"Language `nodejs` is not declared in \[envs.frontend.deps\]",
    ),
]


@pytest.mark.parametrize(
    "case",
    _ADD_FAILURES,
    ids=["rust", "pypi", "unnamed", "no-packages", "missing-env", "env-language"],
)
def test_add_reports_language_errors(workspace: Workspace, case: AddFailure) -> None:
    """A refused add says why and never leaves a half-written table behind."""
    manager = workspace(case.body)
    with pytest.raises(ChefeError, match=case.match):
        manager.dependencies.add(*case.packages, language=case.language, env=case.env)
    if case.absent:
        assert case.absent not in manager.workspace.manifest.read_text()


@pytest.mark.parametrize(
    ("text", "match"),
    [
        (None, "chefe.toml not found"),
        ("[workspace\n", r"invalid TOML.*Expected"),
        ('[deps]\npython = "*"\n', "Field required"),
        (
            """
            [workspace]
            name = "w"

            [nodejs.deps]
            prettier = "*"
            """,
            r"\[deps\]",
        ),
        (
            """
            [workspace]
            name = "w"

            [dev.nodejs.deps]
            prettier = "*"
            """,
            r"\[dev.nodejs\] has no matching package",
        ),
        (
            """
            [workspace]
            name = "w"

            [on.linux-64.nodejs.deps]
            prettier = "*"
            """,
            r"\[on.linux-64.nodejs\] has no matching package",
        ),
        (
            """
            [workspace]
            name = "w"

            [envs.frontend.nodejs.deps]
            prettier = "*"
            """,
            r"\[envs.frontend.nodejs\] has no matching package",
        ),
        (
            """
            [workspace]
            name = "w"

            [envs.default.deps]
            python = "*"
            """,
            r"\[envs.default\] is reserved",
        ),
    ],
)
def test_load_reports_user_errors(tmp_path: Path, text: str | None, match: str) -> None:
    if text is not None:
        (tmp_path / "chefe.toml").write_text(text)
    with pytest.raises(ChefeError, match=match):
        PackageManager(tmp_path).workspace.load()


def test_remove_drops_from_manifest(
    workspace: Workspace, recording_backends: Sequence[tuple[str, ...]]
) -> None:
    manager = workspace(
        """
        [deps]
        python = "*"
        ripgrep = "*"
        """
    )
    manager.dependencies.remove("ripgrep")
    assert "ripgrep" not in manager.workspace.load().deps


def test_pull_mirrors_resolved_versions(workspace: Workspace) -> None:
    """pull reads the generated pixi.toml and bumps the manifest's declared versions."""
    manager = workspace(
        """
        [deps]
        python = ">=3.11"
        """
    )
    manager.environment.sync()
    manager.pixi.manifest.write_text(
        '[workspace]\nname = "w"\n\n[dependencies]\npython = "3.12.5"\n'
    )
    manager.dependencies.pull()
    assert manager.workspace.load().deps["python"].version == "3.12.5"


@pytest.mark.parametrize(("env", "target"), [("", "default"), ("research", "research")])
def test_upgrade_without_packages_refreshes_every_ecosystem_within_constraints(
    *,
    workspace: Workspace,
    recording_backends: Sequence[tuple[str, ...]],
    env: str,
    target: str,
) -> None:
    """A broad upgrade refreshes runtimes, Python, Node, and Cargo without loosening bounds."""
    manager = workspace(
        """
        [deps]
        python = "*"
        nodejs = "*"
        rust = "*"

        [nodejs.deps]
        prettier = "<4"

        [rust.deps]
        ripgrep = "<15"
        """
    )

    manager.dependencies.upgrade(env=env)

    assert ("Pixi", "update", "-e", target) in recording_backends
    assert ("Node", "update") in recording_backends
    assert any(
        call[:2] == ("Cargo", "install") and "ripgrep" in call for call in recording_backends
    )
    assert not any(call[1] == "upgrade" for call in recording_backends)
