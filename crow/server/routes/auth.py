"""Auth routes: email OTP send/verify, logout."""

import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr

from crow.auth.dependencies import get_current_user
from crow.auth.email import send_verification_code
from crow.auth.session import create_session_token

router = APIRouter(prefix="/auth")

# Separate router for /api/me (no prefix)
api_router = APIRouter()


@api_router.get("/api/me")
async def get_me(request: Request):
    """Return current user as JSON (or 401)."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    auth_config = request.app.state.auth_config
    return {
        "id": user["id"],
        "email": user.get("email", ""),
        "display_name": user.get("display_name"),
        "auth_enabled": auth_config.get("enabled", True),
    }

CODE_EXPIRY_MINUTES = 10
MAX_CODES_PER_WINDOW = 3
RATE_LIMIT_MINUTES = 10


class SendCodeRequest(BaseModel):
    email: EmailStr


class VerifyRequest(BaseModel):
    email: EmailStr
    code: str


@router.post("/send-code")
async def send_code(req: SendCodeRequest, request: Request):
    """Generate and send a 6-digit verification code."""
    auth_config = request.app.state.auth_config
    if not auth_config.get("enabled", True):
        raise HTTPException(status_code=404)

    db = request.app.state.db

    # Rate limit
    since = datetime.now(UTC) - timedelta(minutes=RATE_LIMIT_MINUTES)
    count = await db.count_recent_codes(req.email, since)
    if count >= MAX_CODES_PER_WINDOW:
        raise HTTPException(status_code=429, detail="Too many codes requested. Try again later.")

    code = f"{secrets.randbelow(900000) + 100000}"
    expires_at = datetime.now(UTC) + timedelta(minutes=CODE_EXPIRY_MINUTES)
    await db.create_email_code(req.email, code, expires_at)
    await send_verification_code(req.email, code, auth_config)

    return {"status": "sent"}


@router.post("/verify")
async def verify(req: VerifyRequest, request: Request):
    """Verify email code and create session."""
    auth_config = request.app.state.auth_config
    if not auth_config.get("enabled", True):
        raise HTTPException(status_code=404)

    db = request.app.state.db

    valid = await db.verify_email_code(req.email, req.code)
    if not valid:
        raise HTTPException(status_code=400, detail="Invalid or expired code")

    user = await db.get_or_create_user(req.email)
    secret = auth_config.get("session_secret", "")
    token = create_session_token(user["id"], user["email"], secret)

    redirect_to = "/onboarding" if not user.get("display_name") else "/dashboard"
    response = JSONResponse({"status": "ok", "redirect": redirect_to})
    response.set_cookie(
        key="crow_session",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=30 * 24 * 3600,
        secure=request.url.scheme == "https",
    )
    return response


@router.post("/logout")
async def logout(request: Request):
    """Clear session cookie."""
    response = JSONResponse({"status": "ok"})
    response.delete_cookie("crow_session")
    return response
