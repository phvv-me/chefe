import hashlib
import tomllib
from pathlib import Path

from pydantic import ValidationError

from ..core import (
    ChefeError,
    Declared,
    Project,
    current_platform,
    manifest_validation_text,
)
from ..manifest import Manifest, find_manifest


class Workspace:
    """Where a workspace sits on disk and what its manifest says.

    Everything else in this package is handed one of these rather than a path, so the rules for
    finding the manifest, refusing to rewrite an embedded one, and turning a parse failure into
    an actionable message are written once and every command inherits them. It answers only
    those two questions, location and content, and knows no backend, which is what keeps a type
    this widely depended on from collecting the concerns of its callers.
    """

    def __init__(self, root: Path | None = None) -> None:
        # Absolute so the env bin dirs put on PATH stay valid when a backend runs
        # from inside the env: a relative npm path breaks once the cwd changes.
        self.root = (root if root is not None else self.discover()).absolute()
        self.manifest = find_manifest(self.root) or self.root / Project.manifest
        self.out = self.root / Project.env_dir

    @staticmethod
    def discover(start: Path | None = None) -> Path:
        """Walk up from ``start`` (default cwd) to the nearest dir holding the manifest.

        Running chefe from a subdir should still find its workspace, the way git locates `.git`.
        Falls back to ``start`` itself when no manifest is found, so `chefe init` in a fresh dir
        still scaffolds there and `load()` later raises the actionable not-found error.
        """
        start = (start or Path()).absolute()
        for directory in (start, *start.parents):
            if find_manifest(directory) is not None:
                return directory
        return start

    def declared(self, env: str) -> dict[str, Declared]:
        """Every dep declared for ``env`` on this host."""
        return self.load().declared(env, platform=current_platform())

    def digest(self) -> str:
        """A content hash of the manifest, the key that decides whether a compile is current."""
        try:
            return hashlib.sha256(self.manifest.read_bytes()).hexdigest()
        except FileNotFoundError as error:
            raise self.missing() from error

    def editable_manifest(self) -> None:
        """Refuse to rewrite a manifest embedded in `pyproject.toml`.

        `install` and `run` only read, so they work everywhere. The in-place writers
        (`add`/`remove`/`upgrade`) do not: a runtime dep belongs in `[project.dependencies]` and a
        tool in `[tool.chefe]`, so which table a package lands in is ambiguous for an embedded
        manifest. They point at the file to edit by hand rather than guess.
        """
        if self.manifest.name == Project.pyproject:
            raise ChefeError(
                f"`{Project.name}` cannot edit the [tool.{Project.name}] manifest inside "
                f"{Project.pyproject}. "
                f"Edit {Project.pyproject} by hand: runtime deps under [project.dependencies], "
                f"tools and tasks under [tool.{Project.name}]."
            )

    def load(self) -> Manifest:
        """The validated manifest."""
        try:
            return Manifest.load(self.manifest)
        except FileNotFoundError as error:
            raise self.missing() from error
        except tomllib.TOMLDecodeError as error:
            raise ChefeError(f"{self.manifest.name} has invalid TOML: {error}") from error
        except ValidationError as error:
            raise ChefeError(manifest_validation_text(self.manifest, error)) from error

    def missing(self) -> ChefeError:
        """The actionable error for a directory that holds no manifest.

        Every read of the manifest raises this same one, so a command run outside a workspace
        stops with the way out rather than with whichever raw `FileNotFoundError` it hit first.
        """
        return ChefeError(
            f"{self.manifest.name} not found. "
            "Run `chefe init` first, or run chefe from a workspace root."
        )
