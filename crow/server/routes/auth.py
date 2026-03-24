"""Auth routes: email OTP send/verify, logout, instance passphrase gate."""

import secrets
from datetime import UTC, datetime, timedelta

import jwt
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


# ---------------------------------------------------------------------------
# Instance passphrase gate
# ---------------------------------------------------------------------------

GATE_COOKIE_LIFETIME_HOURS = 24


def _check_gate_cookie(request: Request) -> bool:
    """Return True if no passphrase is configured, or if a valid gate cookie is present."""
    auth_config = request.app.state.auth_config
    passphrase = auth_config.get("passphrase", "")
    if not passphrase:
        return True  # no gate configured

    gate_cookie = request.cookies.get("crow_gate", "")
    if not gate_cookie:
        return False

    secret = auth_config.get("session_secret", "")
    try:
        payload = jwt.decode(gate_cookie, secret, algorithms=["HS256"])
        return payload.get("gate") is True
    except jwt.InvalidTokenError:
        return False


@router.get("/gate-status")
async def gate_status(request: Request):
    """Return instance gate configuration (public endpoint)."""
    auth_config = request.app.state.auth_config
    passphrase = auth_config.get("passphrase", "")
    active = bool(passphrase)
    passed = _check_gate_cookie(request) if active else False
    return {
        "instance_gate": active,
        "instance_message": auth_config.get("instance_message", "") if active else "",
        "gate_passed": passed,
    }


class PassphraseRequest(BaseModel):
    passphrase: str


@router.post("/verify-passphrase")
async def verify_passphrase(req: PassphraseRequest, request: Request):
    """Verify the instance passphrase and issue a gate cookie."""
    auth_config = request.app.state.auth_config
    passphrase = auth_config.get("passphrase", "")

    if not passphrase:
        raise HTTPException(status_code=404)

    if not secrets.compare_digest(req.passphrase, passphrase):
        raise HTTPException(status_code=403, detail="Incorrect passphrase")

    secret = auth_config.get("session_secret", "")
    payload = {
        "gate": True,
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(hours=GATE_COOKIE_LIFETIME_HOURS),
    }
    token = jwt.encode(payload, secret, algorithm="HS256")

    response = JSONResponse({"status": "ok"})
    response.set_cookie(
        key="crow_gate",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=GATE_COOKIE_LIFETIME_HOURS * 3600,
        secure=request.url.scheme == "https",
    )
    return response


# ---------------------------------------------------------------------------
# Email OTP
# ---------------------------------------------------------------------------

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

    if not _check_gate_cookie(request):
        raise HTTPException(status_code=403, detail="Passphrase required")

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

    if not _check_gate_cookie(request):
        raise HTTPException(status_code=403, detail="Passphrase required")

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
