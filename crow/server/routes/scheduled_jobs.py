"""Scheduled jobs — create, list, cancel future/recurring agent jobs."""

from datetime import UTC, datetime, timedelta

from croniter import croniter
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from crow.auth.dependencies import get_current_user
from crow.server.routes.jobs import _check_worker_key, _user_id_from_request

router = APIRouter(prefix="/scheduled-jobs")


class SchedulePayload(BaseModel):
    agent_name: str
    input: str
    delay_seconds: int | None = None
    cron: str | None = None
    conversation_id: str | None = None
    user_id: str | None = None
    created_by_job_id: str | None = None


@router.post("")
async def create_scheduled_job(
    payload: SchedulePayload,
    request: Request,
    x_worker_key: str = Header(),
):
    """Worker-facing: create a scheduled job."""
    _check_worker_key(request, x_worker_key)
    db = request.app.state.db

    if payload.cron and payload.delay_seconds:
        raise HTTPException(400, "Provide cron or delay_seconds, not both")
    if not payload.cron and not payload.delay_seconds:
        raise HTTPException(400, "Provide cron or delay_seconds")

    if payload.cron:
        if not croniter.is_valid(payload.cron):
            raise HTTPException(400, f"Invalid cron expression: {payload.cron}")
        run_at = croniter(payload.cron, datetime.now(UTC)).get_next(datetime)
    else:
        run_at = datetime.now(UTC) + timedelta(seconds=payload.delay_seconds)

    from uuid import uuid4

    scheduled_id = uuid4().hex
    result = await db.create_scheduled_job(
        scheduled_id=scheduled_id,
        agent_name=payload.agent_name,
        input_text=payload.input,
        run_at=run_at,
        cron=payload.cron,
        conversation_id=payload.conversation_id,
        user_id=payload.user_id,
        created_by_job_id=payload.created_by_job_id,
    )
    return result


@router.get("")
async def list_scheduled_jobs(request: Request, limit: int = 50):
    """User-facing: list scheduled jobs visible to current user."""
    user = await get_current_user(request)
    uid = _user_id_from_request(request, user)
    db = request.app.state.db
    return await db.list_scheduled_jobs(user_id=uid, limit=limit)


@router.delete("/{scheduled_id}")
async def cancel_scheduled_job(scheduled_id: str, request: Request):
    """User-facing: cancel (complete) a scheduled job."""
    user = await get_current_user(request)
    uid = _user_id_from_request(request, user)
    db = request.app.state.db
    ok = await db.cancel_scheduled_job(scheduled_id, user_id=uid)
    if not ok:
        raise HTTPException(404, "Scheduled job not found or already completed")
    return {"status": "cancelled"}
