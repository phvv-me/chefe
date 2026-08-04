import os
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from filelock import FileLock

from .base import Model


class GeneratedFiles(Model):
    """Atomic generated-file writes guarded by one workspace sync lock."""

    directory: Path

    @contextmanager
    def locked(self) -> Generator[None]:
        """Serialize compilers that target the same generated directory."""
        self.directory.mkdir(exist_ok=True)
        with FileLock(self.directory / ".sync.lock"):
            yield

    def write(self, path: Path, text: str) -> None:
        """Replace one generated text file only after its complete contents reach disk."""
        try:
            if path.read_text(encoding="utf-8") == text:
                return
        except FileNotFoundError:
            pass
        with TemporaryDirectory(dir=path.parent, prefix=f".{path.name}.") as directory:
            temporary = Path(directory) / path.name
            with temporary.open("w", encoding="utf-8") as stream:
                os.fchmod(stream.fileno(), 0o644)
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(path)
