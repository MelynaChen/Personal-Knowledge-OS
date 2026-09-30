from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.database.session import get_session
from app.models import Review
from app.services.review_service import ReviewNotFound, VersionConflict, complete_review

router = APIRouter(prefix="/reviews", tags=["reviews"])


class CompleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    memory_score: int = Field(ge=1, le=5)
    request_key: str = Field(min_length=1, max_length=200)
    expected_version: int = Field(ge=0)


@router.get("/today")
def today(session: Session = Depends(get_session)):
    day = datetime.now(ZoneInfo(get_settings().app_timezone)).date()
    reviews = session.scalars(select(Review).where(Review.status == "Scheduled", Review.next_review_date <= day)
                              .order_by(Review.next_review_date, Review.id))
    return [{"id": r.id, "note_id": r.note_id, "knowledge_node_id": r.knowledge_node_id,
             "next_review_date": r.next_review_date, "review_level": r.review_level,
             "difficulty": r.difficulty, "version": r.version} for r in reviews]


@router.post("/{review_id}/complete")
def complete(review_id: int, body: CompleteRequest, session: Session = Depends(get_session)):
    try:
        with session.begin():
            event = complete_review(session, review_id, body.memory_score, body.request_key, body.expected_version)
        return {"event_id": event.id, "review_id": review_id, "new_level": event.new_level,
                "next_review_date": event.new_next_review_date}
    except ReviewNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except VersionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
