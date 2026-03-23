"""FastAPI auth dependencies."""

import logging

from fastapi import Request
from fastapi.responses import RedirectResponse

from crow.auth.api_keys import hash_api_key
from crow.auth.session import verify_session_token
from crow.db.database import Database

logger = logging.getLogger(__name__)

# Synthetic user returned when auth is disabled
DEFAULT_USER = {
    "id": "default",
    "email": "",
    "display_name": "User",
}


async def get_current_user(request: Request) -> dict | None:
    """Resolve current user from bearer token, session cookie, or default."""
    db: Database = request.app.state.db
    auth_config: dict = request.app.state.auth_config
    auth_enabled = auth_config.get("enabled", False)

    # 1. Check Authorization header (bearer token)
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        key_record = await db.get_api_key_by_hash(hash_api_key(token))
        if key_record:
            await db.touch_api_key(key_record["id"])
            if key_record["user_id"]:
                return await db.get_user(key_record["user_id"])
            return DEFAULT_USER
        # Also check static api_key from crow.yml (when auth disabled)
        static_key = auth_config.get("api_key", "")
        if static_key and token == static_key:
            return DEFAULT_USER
        return None

    # 2. Check session cookie
    session_token = request.cookies.get("crow_session")
    if session_token:
        secret = auth_config.get("session_secret", "")
        payload = verify_session_token(session_token, secret)
        if payload:
            return await db.get_user(payload["sub"])

    # 3. If auth disabled, return default user
    if not auth_enabled:
        return DEFAULT_USER

    return None


async def require_user(request: Request) -> dict | RedirectResponse:
    """Get current user or redirect to login / return 401."""
    user = await get_current_user(request)
    if user:
        return user

    auth_config: dict = request.app.state.auth_config
    auth_enabled = auth_config.get("enabled", False)

    # If bearer token was provided but invalid, 401
    if request.headers.get("authorization", "").startswith("Bearer "):
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="Invalid API key")

    # If auth enabled and no session, redirect to login
    if auth_enabled:
        return RedirectResponse(url="/login", status_code=303)

    return DEFAULT_USER
