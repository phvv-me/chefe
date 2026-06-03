from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import ValidationError


class ChefeError(RuntimeError):
    """A user-facing chefe failure that should be shown without a traceback."""


class ManifestValidationMessage:
    """Format pydantic manifest errors as short CLI guidance."""

    def __init__(self, path: Path, error: ValidationError) -> None:
        self.path = path
        self.error = error

    def text(self) -> str:
        """A readable validation summary for the CLI."""
        details = [self.detail(item) for item in self.error.errors(include_url=False)]
        return "\n".join([f"{self.path.name} is invalid.", *details])

    def detail(self, item: Mapping[str, Any]) -> str:
        """One validation issue, including its TOML location when pydantic knows it."""
        loc = self.location(item)
        message = str(item["msg"]).removeprefix("Value error, ")
        suggestion = self.suggestion(loc, message)
        where = f"{loc}: " if loc else ""
        return f"- {where}{message}{suggestion}"

    def location(self, item: Mapping[str, Any]) -> str:
        """A dotted TOML path from a pydantic error location."""
        loc = item.get("loc", ())
        return ".".join(str(part) for part in loc)

    def suggestion(self, loc: str, message: str) -> str:
        """Extra guidance for the manifest mistakes chefe can identify precisely."""
        if "must have matching entries in [deps]" in message:
            table = self.dep_table(loc)
            return f" Declare the language under {table}, or remove the matching table."
        if "[envs.default] is reserved" in message:
            return (
                " Use the base manifest for the default environment, or choose another env name."
            )
        return ""

    def dep_table(self, loc: str) -> str:
        """The `[deps]` table that owns a runtime-keyed table at this location."""
        parts = loc.split(".")
        if parts and parts[0] == "dev":
            return "[dev.deps]"
        if len(parts) >= 2 and parts[0] == "envs":
            return f"[envs.{parts[1]}.deps]"
        if len(parts) >= 2 and parts[0] == "on":
            return f"[on.{parts[1]}.deps]"
        return "[deps]"
