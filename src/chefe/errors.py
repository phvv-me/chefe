from pathlib import Path

from pydantic import ValidationError
from pydantic_core import ErrorDetails


class ChefeError(RuntimeError):
    """A user-facing chefe failure that should be shown without a traceback."""


def manifest_validation_text(path: Path, error: ValidationError) -> str:
    """A pydantic manifest ValidationError as a short, readable CLI summary.

    Each validator raises a self-contained message (the cause and its fix), so this only tames
    pydantic's shape: it prefixes the file name and tags each issue with its TOML location.
    """
    details = [detail(item) for item in error.errors(include_url=False)]
    return "\n".join([f"{path.name} is invalid.", *details])


def detail(item: ErrorDetails) -> str:
    """One validation issue, prefixed with its TOML location when pydantic knows it."""
    loc = ".".join(str(part) for part in item.get("loc", ()))
    message = item["msg"].removeprefix("Value error, ")
    return f"- {loc}: {message}" if loc else f"- {message}"
