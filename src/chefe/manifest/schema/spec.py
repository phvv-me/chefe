from typing import Self

from pydantic import model_serializer, model_validator

from ...base import FlexModel, Toml


class Spec(FlexModel):
    """A dependency version or inline source table."""

    version: str | None = None
    index: str | None = None

    @model_validator(mode="before")
    @classmethod
    def from_string(cls, data: Toml) -> Toml:
        """Accept a bare version string as a version field."""
        return {"version": data} if isinstance(data, str) else data

    @model_serializer
    def to_toml(self) -> str | dict[str, Toml]:
        """Render the smallest TOML representation that preserves the spec."""
        extra = self.model_extra or {}
        if self.index is None and not extra:
            return self.version or "*"
        named = {
            key: value
            for key, value in (("version", self.version), ("index", self.index))
            if value
        }
        return {**named, **extra}

    def with_index(self, indexes: dict[str, str]) -> Self:
        """Replace a named index with its configured URL."""
        if self.index in indexes:
            return self.model_copy(update={"index": indexes[self.index]})
        return self
