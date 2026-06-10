from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import ValidationError


class ChefeError(RuntimeError):
    """A user-facing chefe failure that should be shown without a traceback."""


class ManifestValidationMessage:
    """Render a pydantic manifest ValidationError as a short, readable CLI summary.

    Each validator raises a self-contained message (the cause and its fix), so this only tames
    pydantic's shape. It prefixes the file name and tags each issue with its TOML location. No
    per-error guidance is reconstructed here. The advice lives where the error is raised.
    """

    def __init__(self, path: Path, error: ValidationError) -> None:
        self.path = path
        self.error = error

    def text(self) -> str:
        """A readable validation summary for the CLI."""
        details = [self.detail(item) for item in self.error.errors(include_url=False)]
        return "\n".join([f"{self.path.name} is invalid.", *details])

    def detail(self, item: Mapping[str, Any]) -> str:
        """One validation issue, prefixed with its TOML location when pydantic knows it."""
        loc = ".".join(str(part) for part in item.get("loc", ()))
        message = str(item["msg"]).removeprefix("Value error, ")
        return f"- {loc}: {message}" if loc else f"- {message}"
