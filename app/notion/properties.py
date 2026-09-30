"""Business objects to Notion page property values."""
from app.models import KnowledgeNode, Note, Review, Task
from app.schemas.common import digest


def split_rich_text_content(value: str, size: int = 1800) -> list[str]:
    if size < 1 or size > 2000:
        raise ValueError("chunk size must be between 1 and 2000")
    return [value[index:index + size] for index in range(0, len(value), size)]


def rich(value: str, *, summary: bool = False) -> dict:
    if summary and len(value) > 1800:
        value = value[:1799] + "…"
    chunks = split_rich_text_content(value)
    if len(chunks) > 100:
        raise ValueError("rich text property exceeds Notion's 100 element request limit")
    return {"rich_text": [{"type": "text", "text": {"content": chunk}} for chunk in chunks]}


def title(value: str) -> dict:
    return {"title": [{"type": "text", "text": {"content": chunk}} for chunk in split_rich_text_content(value)]}


def relation(page_id: str | None) -> dict:
    return {"relation": [{"id": page_id}]} if page_id else {"relation": []}


def metadata(external_id: str, content_hash: str) -> dict:
    return {"External ID": rich(external_id), "Content Hash": rich(content_hash),
            "Sync Status": {"select": {"name": "completed"}}, "Schema Version": {"number": 1}}


def knowledge_properties(node: KnowledgeNode, parent_page_id: str | None) -> dict:
    props = {"Name": title(node.name), "Parent": relation(parent_page_id),
             "Level": {"number": node.level}, "Path": rich(node.display_path, summary=True),
             "Description": rich(node.description, summary=True)}
    if node.category:
        props["Category"] = {"select": {"name": node.category}}
    props.update(metadata(node.node_key, digest({"path": node.path_json, "category": node.category,
                                                 "description": node.description})))
    return props


def task_properties(task: Task, knowledge_page_id: str) -> dict:
    props = {"Name": title(task.name), "Date": {"date": {"start": task.date.isoformat()}},
             "Status": {"status": {"name": "Not started"}}, "Priority": {"select": {"name": task.priority}},
             "Category": {"select": {"name": task.category}},
             "Learning Goal": rich(task.learning_goal, summary=True),
             "Action Steps": rich("\n".join(task.action_steps_json), summary=True),
             "Output Required": rich(task.output_required, summary=True),
             "Knowledge Node": relation(knowledge_page_id), "Source": {"select": {"name": "ChatGPT Plus"}}}
    props.update(metadata(task.external_id, task.content_hash))
    return props


def note_properties(note: Note, knowledge_page_id: str, task_page_id: str) -> dict:
    content = note.content_json
    props = {"Title": title(note.title), "Date": {"date": {"start": note.date.isoformat()}},
             "Knowledge Node": relation(knowledge_page_id), "Related Task": relation(task_page_id)}
    for key, label in (("summary", "Summary"), ("key_concepts", "Key Concepts"),
                       ("detailed_explanation", "Detailed Explanation"), ("examples", "Examples"),
                       ("practice", "Practice"), ("my_understanding", "My Understanding"),
                       ("questions", "Questions"), ("common_mistakes", "Common Mistakes"),
                       ("next_topics", "Next Topics"), ("resources", "Resources")):
        value = content.get(key, "")
        props[label] = rich("\n".join(value) if isinstance(value, list) else value, summary=True)
    props.update(metadata(note.external_id, note.content_hash))
    return props


def review_properties(review: Review, knowledge_page_id: str, note_page_id: str,
                      task_page_id: str) -> dict:
    props = {"Name": title(f"Review: {review.external_id[:12]}"),
             "Knowledge Node": relation(knowledge_page_id), "Related Note": relation(note_page_id),
             "Related Task": relation(task_page_id),
             "Initial Learning Date": {"date": {"start": review.initial_learning_date.isoformat()}},
             "Review Level": {"number": review.review_level},
             "Next Review Date": {"date": {"start": review.next_review_date.isoformat()}},
             "Status": {"select": {"name": review.status}},
             "Difficulty": {"select": {"name": review.difficulty}}}
    if review.memory_score is not None:
        props["Memory Score"] = {"number": review.memory_score}
    props.update(metadata(review.external_id, digest({"level": review.review_level,
                                                       "date": review.next_review_date.isoformat(),
                                                       "score": review.memory_score})))
    return props
