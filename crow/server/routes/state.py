"""State channel — key/value store with SSE streaming."""

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from crow.events.types import STATE_UPDATED, Event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/state")


class StatePayload(BaseModel):
    data: Any


@router.post("/{key}")
async def set_state(key: str, payload: StatePayload, request: Request):
    """Upsert state for a key and broadcast update."""
    db = request.app.state.db
    bus = request.app.state.bus
    row = await db.set_state(key, payload.data)
    await bus.publish(Event(
        type=STATE_UPDATED,
        data={"key": key, "data": payload.data},
    ))
    return {"key": row["key"], "data": row["data"], "updated_at": row["updated_at"].isoformat()}


@router.get("/stream")
async def state_stream(
    request: Request,
    keys: str | None = Query(None, description="Comma-separated state keys to filter"),
):
    """SSE stream of state updates and agent events."""
    bus = request.app.state.bus
    queue: asyncio.Queue[Event] = asyncio.Queue()
    key_filter = set(keys.split(",")) if keys else None

    async def on_state(event: Event) -> None:
        if key_filter and event.data.get("key") not in key_filter:
            return
        await queue.put(event)

    async def on_agent(event: Event) -> None:
        await queue.put(event)

    bus.subscribe(STATE_UPDATED, on_state)
    bus.subscribe("message.*", on_agent)
    bus.subscribe("job.*", on_agent)

    async def generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    data = json.dumps({
                        "type": event.type,
                        "data": event.data,
                        "timestamp": event.timestamp.isoformat(),
                    })
                    yield f"id: {event.id}\nevent: {event.type}\ndata: {data}\n\n"
                except TimeoutError:
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{key}")
async def get_state(key: str, request: Request):
    """Get current state for a key."""
    db = request.app.state.db
    row = await db.get_state(key)
    if not row:
        raise HTTPException(status_code=404, detail="Key not found")
    return {"key": row["key"], "data": row["data"], "updated_at": row["updated_at"].isoformat()}
