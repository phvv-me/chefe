from ...base import Model


class Activation(Model):
    """Scripts sourced when an environment activates."""

    scripts: list[str] = []
