"""SSE streaming — clients subscribe to real-time conversation updates."""

import asyncio
import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from crow.auth.dependencies import get_current_user
from crow.events.types import JOB_FAILED, JOB_PROGRESS, MESSAGE_CHUNK, MESSAGE_RESPONSE, Event
from crow.server.routes.conversations import _verify_conversation_access

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/conversations/{conversation_id}/stream")
async def stream_conversation(conversation_id: str, request: Request):
    """SSE stream of new messages in a conversation."""
    user = await get_current_user(request)
    await _verify_conversation_access(request, conversation_id, user)

    bus = request.app.state.bus
    queue: asyncio.Queue[Event] = asyncio.Queue()

    async def handler(event: Event) -> None:
        if event.data.get("conversation_id") == conversation_id:
            await queue.put(event)

    bus.subscribe(MESSAGE_RESPONSE, handler)
    bus.subscribe(MESSAGE_CHUNK, handler)
    bus.subscribe(JOB_PROGRESS, handler)
    bus.subscribe(JOB_FAILED, handler)

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    # Background jobs: suppress chunks and progress from
                    # conversation stream (they go to activity sidebar via WS).
                    # MESSAGE_RESPONSE still goes through (final result + post_update).
                    is_bg = event.data.get("mode") == "background"
                    if is_bg and event.type in (MESSAGE_CHUNK, JOB_PROGRESS):
                        continue
                    if event.type == MESSAGE_CHUNK:
                        data = json.dumps({
                            "type": event.data.get("type", "text"),
                            "text": event.data.get("text"),
                            "tool_name": event.data.get("tool_name"),
                            "agent_name": event.data.get("agent_name"),
                            "job_id": event.data.get("job_id"),
                        })
                        yield f"id: {event.id}\nevent: chunk\ndata: {data}\n\n"
                    elif event.type == JOB_PROGRESS:
                        data = json.dumps({
                            "status": event.data.get("status"),
                            "agent_name": event.data.get("agent_name"),
                            "job_id": event.data.get("job_id"),
                            "data": event.data.get("data"),
                        })
                        yield f"id: {event.id}\nevent: progress\ndata: {data}\n\n"
                    elif event.type == JOB_FAILED:
                        data = json.dumps({
                            "error": event.data.get("error"),
                            "agent_name": event.data.get("agent_name"),
                            "job_id": event.data.get("job_id"),
                        })
                        yield f"id: {event.id}\nevent: error\ndata: {data}\n\n"
                    else:
                        data = json.dumps({
                            "text": event.data["text"],
                            "agent_name": event.data.get("agent_name"),
                            "timestamp": event.timestamp.isoformat(),
                            "event_id": event.data.get("message_id") or event.id,
                        })
                        yield f"id: {event.id}\nevent: message\ndata: {data}\n\n"
                except TimeoutError:
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
