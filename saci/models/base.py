"""The pydantic base for saci schemas — self-contained (no monorepo deps) so saci
ships as a standalone package."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class FlexModel(BaseModel):
    """Keeps unknown keys (forward-compat + passthrough) and accepts field names or aliases."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)
