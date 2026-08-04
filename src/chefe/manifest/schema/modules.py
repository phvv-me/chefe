from pydantic import ConfigDict

from ...base import Model


class Modules(Model):
    """HPC environment modules loaded in declared order."""

    model_config = ConfigDict(extra="allow", frozen=True, populate_by_name=True)

    def specs(self) -> list[str]:
        """Return module specifications in declaration order."""
        return [f"{name}/{version}" for name, version in (self.model_extra or {}).items()]
