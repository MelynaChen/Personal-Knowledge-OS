import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import StrictDate
from app.schemas.task_schema import TaskInput


class ImportPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal[1] = 1
    date: StrictDate
    tasks: list[TaskInput] = Field(min_length=1, max_length=100)


class RawImport(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    raw_text: str = Field(min_length=1, max_length=5 * 1024 * 1024)


class CommitRequest(RawImport):
    preview_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _invalid_constant(value: str):
    raise ValueError(f"invalid JSON constant: {value}")


def parse_import(raw_text: str) -> ImportPayload:
    raw_text = raw_text.strip()
    if raw_text.startswith("{"):
        candidate = raw_text
    else:
        blocks = re.findall(r"```json\s*\n(.*?)\n```", raw_text, flags=re.DOTALL | re.IGNORECASE)
        all_fences = re.findall(r"```", raw_text)
        if len(blocks) != 1 or len(all_fences) != 2:
            raise ValueError("expected JSON or exactly one json code block")
        candidate = blocks[0]
    data = json.loads(candidate, object_pairs_hook=_unique_pairs, parse_constant=_invalid_constant)
    return ImportPayload.model_validate(data)
