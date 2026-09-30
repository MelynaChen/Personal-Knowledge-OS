"""Import synchronization status, safe retry, and connection diagnostics."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.database.session import SessionLocal, get_session
from app.models import ImportItem, ImportRecord, NotionDatabase
from app.notion.client import NotionConfigurationError, NotionGateway
from app.notion.databases import TITLES, SchemaMismatch, verify_notion_schema
from app.services.sync_read_service import item_operations

router = APIRouter(tags=["sync"])


@router.get("/imports/{import_id}")
def import_status(import_id: int, session: Session = Depends(get_session)):
    record = session.get(ImportRecord, import_id)
    if not record:
        raise HTTPException(404, "import not found")
    items = []
    for item in session.scalars(select(ImportItem).where(ImportItem.import_id == import_id).order_by(ImportItem.item_index)):
        operations = item_operations(session, item.task_id) if item.task_id else []
        sync_status = ("duplicate" if item.status == "duplicate" else
                       "failed" if any(op.status == "failed" for op in operations) else
                       "completed" if operations and all(op.status == "completed" for op in operations) else
                       "processing" if any(op.status == "processing" for op in operations) else "pending")
        items.append({"item_index": item.item_index, "task_id": item.task_id,
                      "local_save_status": item.status, "notion_sync_status": sync_status,
                      "operations": [{"step": op.step, "status": op.status,
                                      "attempts": op.attempts, "last_error": op.last_error} for op in operations]})
    return {"import_id": import_id, "status": record.status, "items": items}


@router.post("/imports/{import_id}/retry")
def retry_import(import_id: int, session: Session = Depends(get_session)):
    with session.begin():
        record = session.get(ImportRecord, import_id)
        if not record:
            raise HTTPException(404, "import not found")
        count = 0
        for item in session.scalars(select(ImportItem).where(ImportItem.import_id == import_id)):
            if not item.task_id:
                continue
            for op in item_operations(session, item.task_id):
                if op.status == "failed" and op.last_error and any(
                    marker in op.last_error for marker in ("rate_limited", "server", "transport")):
                    op.status = "pending"
                    op.next_attempt_at = None
                    op.lease_until = None
                    count += 1
        if count:
            record.status = "pending"
    return {"import_id": import_id, "requeued": count}


def notion_health(session_factory=SessionLocal, gateway=None) -> dict:
    settings = get_settings()
    if not settings.notion_token or not settings.notion_parent_page_id:
        return {"configured": False, "connected": False, "initialized": False,
                "schema_valid": False, "error": "NOTION_TOKEN and NOTION_PARENT_PAGE_ID are required"}
    result = {"configured": True, "connected": False, "initialized": False, "schema_valid": False}
    try:
        gateway = gateway or NotionGateway(settings)
        gateway.retrieve_page(settings.notion_parent_page_id)
        result["connected"] = True
        with session_factory() as session:
            rows = {row.logical_name: row for row in session.scalars(select(NotionDatabase))}
            result["initialized"] = all(name in rows and rows[name].init_step == "completed" for name in TITLES)
        if result["initialized"]:
            verify_notion_schema(session_factory, gateway)
            result["schema_valid"] = True
    except Exception as exc:
        result["error"] = str(exc)[:300]
    return result


@router.get("/notion/health")
def notion_health_route():
    return notion_health()
