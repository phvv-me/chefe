from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from filelock import FileLock

from ...core import Model
from .writer import Writer


class GeneratedFiles(Model):
    """Atomic generated-file writes guarded by one workspace sync lock."""

    directory: Path

    @contextmanager
    def locked(self) -> Generator[Writer]:
        """Serialize compilers that target the same generated directory.

        The :class:`Writer` exists only for the body of this context, so holding the lock is not
        a convention a caller can forget but the only way to reach a write at all.
        """
        self.directory.mkdir(exist_ok=True)
        lock = FileLock(self.directory / ".sync.lock")
        with lock:
            yield Writer(lock)
