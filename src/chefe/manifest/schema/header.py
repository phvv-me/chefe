from ...base import Model


class Header(Model):
    """Workspace identity and solve surface."""

    name: str
    version: str = "0.1.0"
    platforms: list[str] = []
    channels: list[str] = ["conda-forge"]
    dotenv: bool = True
