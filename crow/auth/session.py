"""JWT session token management."""

import logging
from datetime import UTC, datetime, timedelta

import jwt

logger = logging.getLogger(__name__)

SESSION_LIFETIME_DAYS = 30
JOB_TOKEN_LIFETIME_HOURS = 4


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


def create_job_token(
    job_id: str, user_id: str | None, secret: str,
) -> str:
    """Create a short-lived JWT scoped to a job + user.

    Workers use this token to make user-scoped API calls (knowledge, state)
    during job execution. The token is ephemeral and cannot be used to
    escalate privileges — it only carries the user context for data scoping.
    """
    now = datetime.now(UTC)
    payload = {
        "sub": user_id or "",
        "job_id": job_id,
        "type": "job",
        "iat": now,
        "exp": now + timedelta(hours=JOB_TOKEN_LIFETIME_HOURS),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def verify_job_token(token: str, secret: str) -> dict | None:
    """Verify a job-scoped token. Returns payload or None."""
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        if payload.get("type") != "job":
            return None
        return payload
    except jwt.InvalidTokenError:
        return None
