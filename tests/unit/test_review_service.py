from datetime import date

import pytest

from app.models import Note, Review, Task
from app.services.knowledge_service import get_or_create_knowledge_path
from app.services.review_service import VersionConflict, complete_review


def make_review(session):
    node = get_or_create_knowledge_path(session, ["AI"])
    task = Task(external_id="task", date=date(2026, 9, 29), name="Task", category="AI",
                priority="High", learning_goal="Goal", action_steps_json=["Step"],
                output_required="Note", knowledge_node_id=node.id, content_hash="hash")
    session.add(task)
    session.flush()
    note = Note(external_id="note", task_id=task.id, knowledge_node_id=node.id,
                date=task.date, title="Note", summary="Summary", content_json={}, content_hash="hash")
    session.add(note)
    session.flush()
    review = Review(external_id="review", note_id=note.id, task_id=task.id,
                    knowledge_node_id=node.id, initial_learning_date=task.date, review_level=0,
                    next_review_date=task.date, status="Scheduled", difficulty="Medium",
                    version=0, algorithm_version="v1", algorithm_config_json={})
    session.add(review)
    session.commit()
    return review.id


def test_duplicate_review_request(session):
    review_id = make_review(session)
    first = complete_review(session, review_id, 3, "req-1", 0)
    session.commit()
    second = complete_review(session, review_id, 3, "req-1", 0)
    assert second.id == first.id
    assert session.get(Review, review_id).version == 1


def test_review_version_conflict(session):
    review_id = make_review(session)
    complete_review(session, review_id, 3, "req-1", 0)
    session.commit()
    with pytest.raises(VersionConflict):
        complete_review(session, review_id, 4, "req-2", 0)
