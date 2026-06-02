from pydantic import BaseModel, ConfigDict
from typing_extensions import TypeAliasType

# A TOML value: scalars or arbitrarily nested arrays/tables, mirroring what tomllib parses.
# `TypeAliasType` (PEP 695 backport) gives a *named* recursive alias, which both pydantic's
# schema builder and mypy resolve without the infinite recursion a bare forward-ref triggers.
Toml = TypeAliasType("Toml", "str | int | float | bool | list[Toml] | dict[str, Toml]")


class Model(BaseModel):
    """Strict, frozen base: only declared fields (unknown keys error), immutable after load."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class FlexModel(BaseModel):
    """Frozen base for specs that delegate unknown keys to pixi/uv, kept as extras."""

    model_config = ConfigDict(extra="allow", frozen=True, populate_by_name=True)
