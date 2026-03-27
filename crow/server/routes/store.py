"""Agent store — persistent structured key-value store for agents."""

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from crow.auth.dependencies import get_current_user

router = APIRouter(prefix="/api/store")


class StorePayload(BaseModel):
    data: Any


class StoreUpdatePayload(BaseModel):
    path: str
    value: Any


def _resolve_uid(request: Request, user: dict | None) -> str | None:
    auth_enabled = request.app.state.auth_config.get("enabled", True)
    if not auth_enabled or not user:
        return None
    if user.get("id") == "default":
        return None
    return user["id"]


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
    row = await db.store_set(namespace, key, payload.data, user_id=uid)
    return {
        "namespace": namespace,
        "key": key,
        "data": row["data"],
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
