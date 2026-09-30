"""Immutable first-write page bodies under an application-owned toggle."""
import json

from app.notion.properties import split_rich_text_content

CONTAINER_MARKER = "Personal Knowledge OS • managed content"


def _rich(value: str) -> list[dict]:
    return [{"type": "text", "text": {"content": part}} for part in split_rich_text_content(value)]


def paragraph(value: str) -> dict:
    return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": _rich(value)}}


def heading(value: str) -> dict:
    return {"object": "block", "type": "heading_2", "heading_2": {"rich_text": _rich(value)}}


def bullet(value: str) -> dict:
    return {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": _rich(value)}}


def container_block() -> dict:
    return {"object": "block", "type": "toggle", "toggle": {"rich_text": _rich(CONTAINER_MARKER)}}


def task_blocks(task, knowledge_path: list[str]) -> list[dict]:
    blocks = [heading("Learning Goal"), paragraph(task.learning_goal), heading("Action Steps")]
    blocks.extend(bullet(step) for step in task.action_steps_json)
    blocks.extend([heading("Output Required"), paragraph(task.output_required),
                   heading("Knowledge Path"), paragraph(" / ".join(knowledge_path)),
                   heading("Source"), paragraph("ChatGPT Plus")])
    return blocks


def note_blocks(note) -> list[dict]:
    fields = (("summary", "Summary"), ("key_concepts", "Key Concepts"),
              ("detailed_explanation", "Detailed Explanation"), ("examples", "Examples"),
              ("practice", "Practice"), ("my_understanding", "My Understanding"),
              ("questions", "Questions"), ("common_mistakes", "Common Mistakes"),
              ("next_topics", "Next Topics"), ("resources", "Resources"))
    blocks = []
    for key, label in fields:
        blocks.append(heading(label))
        value = note.content_json.get(key, "")
        if isinstance(value, list):
            blocks.extend(bullet(item) for item in value)
        elif value:
            for chunk in split_rich_text_content(value):
                blocks.append(paragraph(chunk))
    return blocks


def block_batches(blocks: list[dict], content_hash: str, max_blocks: int = 50) -> list[list[dict]]:
    batches = []
    current = []
    for block in blocks:
        prospective = current + [block]
        if current and (len(prospective) >= max_blocks or len(json.dumps(prospective, ensure_ascii=False).encode("utf-8")) > 350_000):
            batches.append(current)
            current = []
        current.append(block)
    if current:
        batches.append(current)
    return [[paragraph(f"PKOS:BATCH:{content_hash}:{index}")] + batch for index, batch in enumerate(batches)]
