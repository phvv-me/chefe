from ....core import Model
from .spec import Spec


class Registry(Model):
    """A dependency registry table."""

    deps: dict[str, Spec] = {}
