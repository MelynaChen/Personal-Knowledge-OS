from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.models import Review, ReviewEvent
from app.services.review_scheduler import SchedulerConfig, schedule_review


class VersionConflict(Exception):
    pass


class ReviewNotFound(Exception):
    pass


def complete_review(session: Session, review_id: int, memory_score: int,
                    request_key: str, expected_version: int) -> ReviewEvent:
    existing_event = session.scalar(select(ReviewEvent).where(ReviewEvent.review_id == review_id,
                                                            ReviewEvent.request_key == request_key))
    if existing_event:
        return existing_event
    review = session.get(Review, review_id)
    if review is None:
        raise ReviewNotFound(review_id)
    if review.version != expected_version:
        raise VersionConflict(f"expected version {expected_version}; current version {review.version}")
    now = datetime.now(ZoneInfo(get_settings().app_timezone))
    config = SchedulerConfig(**review.algorithm_config_json)
    result = schedule_review(review.review_level, memory_score, now.date(), config)
    old_level, old_date = review.review_level, review.next_review_date
    changed = session.execute(update(Review).where(Review.id == review_id, Review.version == expected_version)
                              .values(review_level=result.level, next_review_date=result.next_review_date,
                                      memory_score=memory_score, version=expected_version + 1))
    if changed.rowcount != 1:
        raise VersionConflict("review was updated concurrently")
    event = ReviewEvent(review_id=review_id, request_key=request_key, memory_score=memory_score,
                        old_level=old_level, new_level=result.level, old_next_review_date=old_date,
                        new_next_review_date=result.next_review_date, completed_at=now,
                        algorithm_version=review.algorithm_version)
    session.add(event)
    session.flush()
    return event
