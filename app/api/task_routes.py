"""Small local task-progress API for the daily dashboard."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.database.session import get_session
from app.models import Task

router = APIRouter(prefix="/tasks", tags=["tasks"])


class TaskStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    status: Literal["Not started", "In progress", "Done"]


@router.patch("/{task_id}/status")
def update_task_status(task_id: int, body: TaskStatusRequest, session: Session = Depends(get_session)):
    with session.begin():
        task = session.get(Task, task_id)
        if task is None:
            raise HTTPException(404, "task not found")
        task.status = body.status
    return {"task_id": task_id, "status": task.status}
