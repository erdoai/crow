"""Push notification device token registration."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from crow.auth.dependencies import get_current_user

router = APIRouter(prefix="/push")


class RegisterPayload(BaseModel):
    device_token: str
    platform: str = "apns"


@router.post("/register")
async def register_device(payload: RegisterPayload, request: Request):
    """Register a device token for push notifications."""
    auth_enabled = request.app.state.auth_config.get("enabled", True)
    user = await get_current_user(request)
    if auth_enabled and (not user or user["id"] == "default"):
        raise HTTPException(401, "Authentication required")

    db = request.app.state.db
    result = await db.register_device_token(
        user_id=user["id"],
        token=payload.device_token,
        platform=payload.platform,
    )
    return {"status": "registered", **result}


@router.delete("/register/{token}")
async def unregister_device(token: str, request: Request):
    """Unregister a device token."""
    db = request.app.state.db
    ok = await db.unregister_device_token(token)
    if not ok:
        raise HTTPException(404, "Token not found")
    return {"status": "unregistered"}
