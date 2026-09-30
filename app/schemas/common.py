import hashlib
import json
import re
import unicodedata
from datetime import date
from typing import Any, Annotated

from pydantic import BeforeValidator


def identity(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("identity must be a string")
    result = unicodedata.normalize("NFC", value.strip())
    if not result:
        raise ValueError("identity cannot be empty")
    return result


Identity = Annotated[str, BeforeValidator(identity)]


def strict_date(value: Any) -> date:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("date must be YYYY-MM-DD")
    return date.fromisoformat(value)


StrictDate = Annotated[date, BeforeValidator(strict_date)]


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
