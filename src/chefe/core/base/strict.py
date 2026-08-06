from pydantic import BaseModel, ConfigDict


class Model(BaseModel):
    """Strict, frozen base: only declared fields (unknown keys error), immutable after load."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)
