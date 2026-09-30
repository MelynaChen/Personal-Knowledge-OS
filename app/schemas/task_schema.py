from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import Identity, identity
from app.schemas.note_schema import NoteInput
from app.schemas.review_schema import ReviewInput


class TaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    name: Identity = Field(max_length=200)
    category: Identity = Field(max_length=100)
    priority: Literal["Low", "Medium", "High"]
    knowledge_path: list[Identity] = Field(min_length=1)
    learning_goal: str = Field(min_length=1)
    action_steps: list[str] = Field(min_length=1)
    output_required: str = Field(min_length=1)
    note: NoteInput
    review: ReviewInput

    @field_validator("knowledge_path")
    @classmethod
    def validate_path(cls, path: list[str]) -> list[str]:
        if any(len(part) > 200 for part in path):
            raise ValueError("knowledge path segment exceeds 200 characters")
        return path

    @field_validator("category")
    @classmethod
    def valid_category(cls, value: str) -> str:
        if "," in value:
            raise ValueError("category cannot contain a comma")
        return value

    @field_validator("action_steps")
    @classmethod
    def validate_steps(cls, steps: list[str]) -> list[str]:
        if any(not step.strip() for step in steps):
            raise ValueError("action steps cannot be blank")
        return steps
