"""WebSocket endpoint with auto-reconnect catch-up.

Replaces the SSE state stream. Clients connect, receive live events,
and on reconnect provide last_seq to replay missed events from an
in-memory rolling buffer.

Auth: clients first call POST /ws/token (authed via cookie/bearer)
to get a short-lived ephemeral token, then connect to /ws?token=...
"""

import asyncio
import logging
import time
from collections import defaultdict
from uuid import uuid4

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect

from crow.auth.dependencies import get_current_user
from crow.events.types import STATE_UPDATED, Event

logger = logging.getLogger(__name__)

router = APIRouter()

# Ephemeral WS tokens: token -> (user_dict, expires_ts)
_ws_tokens: dict[str, tuple[dict, float]] = {}
WS_TOKEN_TTL = 30  # seconds — just long enough to open the connection

# Per-user rolling event buffer for catch-up on reconnect.
MAX_BUFFER = 500
_buffers: dict[str, list[dict]] = defaultdict(list)
_seq_counter = 0


@router.post("/ws/token")
async def create_ws_token(request: Request):
    """Exchange an authenticated session for a short-lived WS token."""
    user = await get_current_user(request)
    if not user:
        from fastapi import HTTPException
        raise HTTPException(401, "Unauthorized")
    token = uuid4().hex
    _ws_tokens[token] = (user, time.time() + WS_TOKEN_TTL)
    return {"token": token, "ttl": WS_TOKEN_TTL}


def _next_seq() -> int:
    global _seq_counter
    _seq_counter += 1
    return _seq_counter


def _buffer_event(user_key: str, event_dict: dict) -> None:
    """Add event to per-user rolling buffer."""
    event_dict["seq"] = _next_seq()
    buf = _buffers[user_key]
    buf.append(event_dict)
    if len(buf) > MAX_BUFFER:
        del buf[: len(buf) - MAX_BUFFER]


def _events_since(user_key: str, last_seq: int) -> list[dict]:
    """Return buffered events newer than last_seq."""
    return [ev for ev in _buffers.get(user_key, []) if ev["seq"] > last_seq]


async def _authenticate_ws(websocket: WebSocket) -> dict | None:
    """Authenticate via ephemeral token from POST /ws/token."""
    auth_enabled = websocket.app.state.auth_config.get("enabled", True)
    if not auth_enabled:
        return {"id": "default", "email": "", "display_name": "User"}

    token = websocket.query_params.get("token", "")
    if not token:
        return None

    entry = _ws_tokens.pop(token, None)  # single-use
    if not entry:
        return None
    user, expires = entry
    if time.time() > expires:
        return None

    # Garbage-collect expired tokens
    now = time.time()
    expired = [k for k, (_, exp) in _ws_tokens.items() if now > exp]
    for k in expired:
        _ws_tokens.pop(k, None)

    return user


def _user_key(user: dict, auth_enabled: bool) -> str:
    if auth_enabled and user["id"] != "default":
        return user["id"]
    return "__global__"


def _serialise_event(event: Event) -> dict:
    return {
        "type": event.type,
        "data": event.data,
        "timestamp": event.timestamp.isoformat(),
        "id": event.id,
    }


@router.websocket("/ws")
async def ws_activity(websocket: WebSocket):
    """Activity WebSocket with catch-up replay.

    Query params:
      token  - API key or session JWT (optional if cookie present)
      last_seq - last seen seq number for catch-up (default 0)
    """
    await websocket.accept()

    user = await _authenticate_ws(websocket)
    if not user:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    auth_enabled = websocket.app.state.auth_config.get("enabled", True)
    ukey = _user_key(user, auth_enabled)
    uid = user["id"] if auth_enabled and user["id"] != "default" else None
    last_seq = int(websocket.query_params.get("last_seq", "0"))
    bus = websocket.app.state.bus

    # Replay missed events
    if last_seq > 0:
        for ev in _events_since(ukey, last_seq):
            try:
                await websocket.send_json(ev)
            except WebSocketDisconnect:
                return

    # Subscribe to live events
    queue: asyncio.Queue[dict] = asyncio.Queue()

    async def on_state(event: Event) -> None:
        if event.data.get("user_id") != uid:
            return
        await queue.put(_serialise_event(event))

    async def on_agent(event: Event) -> None:
        await queue.put(_serialise_event(event))

    bus.subscribe(STATE_UPDATED, on_state)
    bus.subscribe("message.*", on_agent)
    bus.subscribe("job.*", on_agent)

    ping_task = asyncio.create_task(_ping_loop(websocket))
    try:
        while True:
            try:
                event_dict = await asyncio.wait_for(
                    queue.get(), timeout=30.0
                )
                _buffer_event(ukey, event_dict)
                await websocket.send_json(event_dict)
            except TimeoutError:
                pass  # ping_loop handles keepalive
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("WebSocket error")
    finally:
        ping_task.cancel()


async def _ping_loop(websocket: WebSocket):
    """Ping every 25s to keep the connection alive through proxies."""
    try:
        while True:
            await asyncio.sleep(25)
            await websocket.send_json(
                {"type": "ping", "ts": time.time(), "seq": 0}
            )
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
