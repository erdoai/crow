"""JWT session token management."""

import logging
from datetime import UTC, datetime, timedelta

import jwt

logger = logging.getLogger(__name__)

SESSION_LIFETIME_DAYS = 30


def create_session_token(user_id: str, email: str, secret: str) -> str:
    """Create a signed JWT session token."""
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "email": email,
        "iat": now,
        "exp": now + timedelta(days=SESSION_LIFETIME_DAYS),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def verify_session_token(token: str, secret: str) -> dict | None:
    """Verify and decode a session token. Returns payload or None."""
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.InvalidTokenError:
        return None
