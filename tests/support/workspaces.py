import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from pytest_subprocess import FakeProcess

from chefe.manifest import Document

# The platform is pinned because the host default would make generated manifests differ
# between machines and break every snapshot comparison.
_HEADER = '[workspace]\nname = "w"\nplatforms = ["linux-64"]\n\n'


@contextmanager
def document_from_toml(text: str = '[workspace]\nname = "w"\n') -> Iterator[Document]:
    """Create an on-disk editable manifest from TOML text for one test example."""
    with tempfile.TemporaryDirectory(prefix="chefe-") as root:
        path = Path(root) / "chefe.toml"
        path.write_text(text)
        yield Document(path)


def write_manifest(root: Path, body: str = "") -> Path:
    """Drop a `chefe.toml` (header prepended) under ``root`` and return its path."""
    path = root / "chefe.toml"
    path.write_text(_HEADER + body)
    return path


def executable(directory: Path, name: str) -> Path:
    """Create ``directory`` and drop a runnable stub named ``name`` inside it."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text("#!/bin/sh\n")
    path.chmod(0o755)
    return path


def ecosystem_workspace(root: Path, fp: FakeProcess, pixi: str) -> Path:
    """Declare conda, python, nodejs and rust deps under ``root`` and stub every binary they run.

    Returns the global env prefix whose `bin/` holds the second-stage installers, so a caller can
    assert against the exact argv each of them receives.
    """
    (root / "chefe.toml").write_text(
        """[workspace]
name = "demo"
platforms = ["linux-64"]
[deps]
ripgrep = "*"
python = "*"
nodejs = "*"
rust = "*"
[python.deps]
ruff = ">=0.6"
[nodejs.deps]
prettier = ">=3"
[rust.deps]
bat = "*"
"""
    )
    prefix = root / "pixi" / "envs" / "demo"
    for argv0 in (pixi, *(str(prefix / "bin" / tool) for tool in ("python", "npm", "cargo"))):
        fp.register([argv0, fp.any()], stdout="")
    return prefix


def conda_workspace(root: Path) -> None:
    """Drop a `chefe.toml` whose `[workspace] name` defaults the global env to `life`."""
    path = root / "chefe.toml"
    path.write_text('[workspace]\nname = "life"\nplatforms = ["linux-64"]\n[deps]\n')
