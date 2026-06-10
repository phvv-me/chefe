from collections.abc import Mapping, Sequence

from pydantic import BaseModel, ConfigDict

# A TOML value: scalars or arbitrarily nested arrays/tables, mirroring what tomllib parses.
# A PEP 695 `type` statement gives a *named* recursive alias, which both pydantic's
# schema builder and mypy resolve without the infinite recursion a bare forward-ref triggers.
# The containers are covariant (`Sequence`/`Mapping`, not `list`/`dict`) so a concrete
# `list[str]` or `dict[str, str]` assigns into a `Toml` slot without a cast.
type Toml = str | int | float | bool | Sequence[Toml] | Mapping[str, Toml]


class Model(BaseModel):
    """Strict, frozen base: only declared fields (unknown keys error), immutable after load."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class FlexModel(BaseModel):
    """Frozen base for specs that delegate unknown keys to pixi/uv, kept as extras."""

    model_config = ConfigDict(extra="allow", frozen=True, populate_by_name=True)
