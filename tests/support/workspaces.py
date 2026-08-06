import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

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


def conda_workspace(root: Path) -> None:
    """Drop a `chefe.toml` whose `[workspace] name` defaults the global env to `life`."""
    path = root / "chefe.toml"
    path.write_text('[workspace]\nname = "life"\nplatforms = ["linux-64"]\n[deps]\n')
