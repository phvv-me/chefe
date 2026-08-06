from pydantic import BaseModel, ConfigDict


class FlexModel(BaseModel):
    """Frozen base for specs that delegate unknown keys to pixi/uv, kept as extras."""

    model_config = ConfigDict(extra="allow", frozen=True, populate_by_name=True)
