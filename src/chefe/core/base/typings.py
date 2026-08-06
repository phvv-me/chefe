# A TOML value as tomllib parses it. The PEP 695 `type` statement names the recursive alias so
# pydantic and mypy resolve it, and covariant `Sequence`/`Mapping` accept a concrete `list[str]`.
from collections.abc import Mapping, Sequence

type Toml = str | int | float | bool | Sequence[Toml] | Mapping[str, Toml]

# The table form carries only `run`, `depends` and `dir`, which the recursive `Toml` value cannot
# pin down, so every reader of a task table must treat any other key as unsupported.
type Task = str | dict[str, Toml]
