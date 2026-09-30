from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import Identity


class NoteInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    title: Identity = Field(max_length=200)
    summary: str
    key_concepts: list[str]
    detailed_explanation: str
    examples: list[str]
    practice: list[str]
    my_understanding: str
    questions: list[str]
    common_mistakes: list[str]
    next_topics: list[str]
    resources: list[str]

    @field_validator("key_concepts", "examples", "practice", "questions", "common_mistakes", "next_topics", "resources")
    @classmethod
    def nonblank_list(cls, value: list[str]) -> list[str]:
        if any(not item.strip() for item in value):
            raise ValueError("list items cannot be blank")
        return value
