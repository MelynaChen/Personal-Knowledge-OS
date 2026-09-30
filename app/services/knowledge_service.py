from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import KnowledgeNode
from app.schemas.common import digest, identity


class CategoryConflict(ValueError):
    pass


def get_or_create_knowledge_path(session: Session, path: list[str], category: str | None = None) -> KnowledgeNode:
    if not path:
        raise ValueError("knowledge path cannot be empty")
    parts = [identity(item) for item in path]
    category = identity(category) if category is not None else None
    parent_id = None
    node = None
    for level, name in enumerate(parts):
        query = select(KnowledgeNode).where(KnowledgeNode.parent_id == parent_id,
                                            KnowledgeNode.normalized_name == name)
        node = session.scalar(query)
        if node is None:
            node = KnowledgeNode(parent_id=parent_id, name=name, normalized_name=name,
                                 path_json=parts[:level + 1], display_path=" / ".join(parts[:level + 1]),
                                 level=level, node_key=digest(parts[:level + 1]), category=category)
            try:
                with session.begin_nested():
                    session.add(node)
                    session.flush()
            except IntegrityError:
                node = session.scalar(query)
                if node is None:
                    raise
        if category is not None and node.category not in (None, category):
            raise CategoryConflict(f"category conflict for {' / '.join(parts[:level + 1])}")
        parent_id = node.id
    return node
