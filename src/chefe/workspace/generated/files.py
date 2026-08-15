from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from filelock import FileLock

from ...core import Model
from .writer import Writer

# One FileLock instance per generated directory, shared across every
# in-process acquisition. filelock is reentrant per INSTANCE, so the runtime
# may open a transaction (stale-check plus recompile) while `provision`
# already holds the same lock around the whole install, where two separate
# instances on the same path would deadlock. Cross-process exclusion is
# unchanged, it lives in the OS lock underneath.
_LOCKS: dict[Path, FileLock] = {}


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
        key = self.directory.resolve()
        lock = _LOCKS.setdefault(key, FileLock(key / ".sync.lock"))
        with lock:
            yield Writer(lock)
