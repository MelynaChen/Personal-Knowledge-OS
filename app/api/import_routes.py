from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.database.session import get_session
from app.schemas.import_schema import CommitRequest, RawImport
from app.services.import_service import preview_import
from app.services.commit_service import ImportConflict, PreviewMismatch, commit_import

router = APIRouter(prefix="/import", tags=["import"])


@router.post("/preview")
def preview(body: RawImport, session: Session = Depends(get_session)):
    try:
        return preview_import(session, body.raw_text)
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/commit", status_code=202)
def commit(body: CommitRequest, session: Session = Depends(get_session)):
    try:
        with session.begin():
            record = commit_import(session, body.raw_text, body.preview_hash)
        return {"import_id": record.id, "sync_status": record.status}
    except PreviewMismatch as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ImportConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
