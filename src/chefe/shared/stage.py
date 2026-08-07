from collections.abc import Callable, Mapping
from pathlib import Path
from typing import NamedTuple

from ..manifest import Spec


class SecondStage(NamedTuple):
    """One toolchain installed after conda, and how its specs are spelled for its installer."""

    toolchain: str
    install: Callable[[Path, list[str]], None]
    specs: Callable[[Mapping[str, Spec]], list[str]]
