import json

import pytest
from pydantic import ValidationError

from app.schemas.import_schema import parse_import
from app.services.import_service import task_content_hash, task_external_id


def test_strict_json(sample_json):
    assert parse_import(sample_json).tasks[0].priority == "High"
    assert parse_import(f"```json\n{sample_json}\n```").date.isoformat() == "2026-09-29"
    with pytest.raises(ValueError):
        parse_import("hello world")
    with pytest.raises(ValueError):
        parse_import("{\"date\":NaN}")


def test_duplicate_json_keys():
    with pytest.raises(ValueError, match="duplicate"):
        parse_import('{"date":"2026-09-29","date":"2026-09-30","tasks":[]}')


@pytest.mark.parametrize("bad", ["2026-9-29", "2026-02-30", "2026-09-29T00:00:00"])
def test_invalid_date(sample_payload, bad):
    sample_payload["date"] = bad
    with pytest.raises(ValidationError):
        parse_import(json.dumps(sample_payload))


def test_extra_fields(sample_payload):
    sample_payload["unknown"] = 1
    with pytest.raises(ValidationError):
        parse_import(json.dumps(sample_payload))


def test_boolean_strictness(sample_payload):
    sample_payload["tasks"][0]["review"]["enabled"] = "true"
    with pytest.raises(ValidationError):
        parse_import(json.dumps(sample_payload))


def test_unicode_normalization(sample_payload):
    sample_payload["tasks"][0]["name"] = "  Cafe\u0301  "
    task = parse_import(json.dumps(sample_payload)).tasks[0]
    assert task.name == "Café"


def test_task_external_id_stability(sample_payload):
    a = parse_import(json.dumps(sample_payload))
    sample_payload["tasks"][0]["name"] = "  学习 RAG 中的 Embedding  "
    b = parse_import(json.dumps(sample_payload))
    assert task_external_id(1, a.date, a.tasks[0]) == task_external_id(1, b.date, b.tasks[0])


def test_task_external_id_changes_with_path(sample_payload):
    a = parse_import(json.dumps(sample_payload))
    sample_payload["tasks"][0]["knowledge_path"][-1] = "Vector"
    b = parse_import(json.dumps(sample_payload))
    assert task_external_id(1, a.date, a.tasks[0]) != task_external_id(1, b.date, b.tasks[0])


def test_content_hash(sample_payload):
    a = parse_import(json.dumps(sample_payload)).tasks[0]
    first = task_content_hash(a)
    sample_payload["tasks"][0]["note"]["summary"] = "变化"
    b = parse_import(json.dumps(sample_payload)).tasks[0]
    assert first != task_content_hash(b)
    assert first == task_content_hash(a)
