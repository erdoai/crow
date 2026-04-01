"""Agent store — persistent structured key-value store for agents."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from crow.auth.dependencies import get_current_user
from crow.auth.session import verify_job_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/store")


class StorePayload(BaseModel):
    data: Any


class StoreUpdatePayload(BaseModel):
    path: str
    value: Any


def _resolve_uid(request: Request, user: dict | None) -> str | None:
    """Resolve user_id from session/API-key user OR worker job token."""
    auth_enabled = request.app.state.auth_config.get("enabled", True)
    if not auth_enabled:
        return None

    # Session / API-key user
    if user and user.get("id") != "default":
        return user["id"]

    # Worker job token (carries the owning user's ID)
    token = request.headers.get("x-job-token")
    if token:
        secret = request.app.state.auth_config.get("session_secret", "")
        payload = verify_job_token(token, secret)
        if payload and payload.get("sub"):
            return payload["sub"]

    return None


@router.get("")
async def list_namespaces(request: Request):
    """List all namespaces with key counts."""
    user = await get_current_user(request)
    uid = _resolve_uid(request, user)
    db = request.app.state.db
    rows = await db.store_namespaces(user_id=uid)
    return [
        {
            "namespace": r["namespace"],
            "key_count": r["key_count"],
            "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
        }
        for r in rows
    ]


@router.get("/{namespace}")
async def list_keys(namespace: str, request: Request):
    """List all keys in a namespace."""
    user = await get_current_user(request)
    uid = _resolve_uid(request, user)
    db = request.app.state.db
    rows = await db.store_list(namespace, user_id=uid)
    return [
        {"key": r["key"], "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None}
        for r in rows
    ]


@router.get("/{namespace}/{key}")
async def get_value(namespace: str, key: str, request: Request):
    """Read a value from the store."""
    user = await get_current_user(request)
    uid = _resolve_uid(request, user)
    db = request.app.state.db
    row = await db.store_get(namespace, key, user_id=uid)
    if not row:
        raise HTTPException(404, "Key not found")
    return {"namespace": namespace, "key": key, "data": row["data"]}


@router.post("/{namespace}/{key}")
async def set_value(
    namespace: str, key: str, payload: StorePayload, request: Request
):
    """Write/upsert a value in the store."""
    user = await get_current_user(request)
    uid = _resolve_uid(request, user)
    db = request.app.state.db
    logger.info(
        "store_set %s/%s: input type=%s",
        namespace, key, type(payload.data).__name__,
    )
    row = await db.store_set(namespace, key, payload.data, user_id=uid)
    stored_type = type(row["data"]).__name__
    if isinstance(payload.data, list) and not isinstance(row["data"], list):
        logger.error(
            "store_set %s/%s: DATA TYPE MISMATCH — sent %s, got back %s",
            namespace, key, type(payload.data).__name__, stored_type,
        )
    return {
        "namespace": namespace,
        "key": key,
        "data": row["data"],
        "updated_at": row["updated_at"].isoformat(),
    }


class StoreAppendPayload(BaseModel):
    items: list


@router.post("/{namespace}/{key}/append")
async def append_value(
    namespace: str, key: str, payload: StoreAppendPayload, request: Request
):
    """Atomically append items to an array in the store.

    Creates the key with the items if it doesn't exist.
    """
    user = await get_current_user(request)
    uid = _resolve_uid(request, user)
    db = request.app.state.db
    # Check existing data type before append
    existing = await db.store_get(namespace, key, user_id=uid)
    if existing and not isinstance(existing["data"], list):
        logger.warning(
            "store_append %s/%s: existing data is %s, not array — resetting",
            namespace, key, type(existing["data"]).__name__,
        )
        await db.store_set(namespace, key, [], user_id=uid)

    row = await db.store_append(namespace, key, payload.items, user_id=uid)
    count = len(row["data"]) if isinstance(row["data"], list) else 0
    return {
        "namespace": namespace,
        "key": key,
        "count": count,
        "updated_at": row["updated_at"].isoformat(),
    }


@router.patch("/{namespace}/{key}")
async def update_value(
    namespace: str, key: str, payload: StoreUpdatePayload, request: Request
):
    """Partial update via JSON path (dot notation)."""
    user = await get_current_user(request)
    uid = _resolve_uid(request, user)
    db = request.app.state.db
    row = await db.store_update(
        namespace, key, payload.path, payload.value, user_id=uid
    )
    if not row:
        raise HTTPException(404, "Key not found")
    return {
        "namespace": namespace,
        "key": key,
        "data": row["data"],
        "updated_at": row["updated_at"].isoformat(),
    }


@router.delete("/{namespace}/{key}")
async def delete_value(namespace: str, key: str, request: Request):
    """Delete a key from the store."""
    user = await get_current_user(request)
    uid = _resolve_uid(request, user)
    db = request.app.state.db
    ok = await db.store_delete(namespace, key, user_id=uid)
    if not ok:
        raise HTTPException(404, "Key not found")
    return {"status": "deleted"}
