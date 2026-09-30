from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictBool


class ReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    enabled: StrictBool
    difficulty: Literal["Easy", "Medium", "Hard"]
