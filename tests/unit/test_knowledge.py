import pytest
from sqlalchemy.exc import IntegrityError

from app.models import KnowledgeNode
from app.services.knowledge_service import CategoryConflict, get_or_create_knowledge_path


def test_root_node_uniqueness(session):
    get_or_create_knowledge_path(session, ["AI"])
    session.commit()
    session.add(KnowledgeNode(name="AI", normalized_name="AI", path_json=["AI"],
                              display_path="AI", level=0, node_key="another", category=None))
    with pytest.raises(IntegrityError):
        session.flush()


def test_child_node_uniqueness(session):
    get_or_create_knowledge_path(session, ["AI", "LLM"])
    session.commit()
    root = get_or_create_knowledge_path(session, ["AI"])
    session.add(KnowledgeNode(parent_id=root.id, name="LLM", normalized_name="LLM",
                              path_json=["AI", "LLM"], display_path="AI / LLM",
                              level=1, node_key="another", category=None))
    with pytest.raises(IntegrityError):
        session.flush()


def test_get_or_create_knowledge_path(session):
    node = get_or_create_knowledge_path(session, ["AI", "LLM", "RAG", "Embedding"], "AI")
    session.commit()
    same = get_or_create_knowledge_path(session, ["AI", "LLM", "RAG", "Embedding"], "AI")
    assert same.id == node.id and node.level == 3
    assert node.path_json == ["AI", "LLM", "RAG", "Embedding"]


def test_same_name_different_parent(session):
    left = get_or_create_knowledge_path(session, ["AI", "Embedding"])
    right = get_or_create_knowledge_path(session, ["Search", "Embedding"])
    assert left.id != right.id


def test_category_conflict(session):
    get_or_create_knowledge_path(session, ["AI"], "AI")
    with pytest.raises(CategoryConflict):
        get_or_create_knowledge_path(session, ["AI"], "Math")
