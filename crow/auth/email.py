"""Email verification via Resend."""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"


async def send_verification_code(
    email: str, code: str, auth_config: dict[str, Any]
) -> None:
    """Send a 6-digit verification code via Resend, or log it in dev mode."""
    resend_key = auth_config.get("resend", {}).get("api_key", "")
    resend_from = auth_config.get("resend", {}).get("from", "crow <noreply@erdo.ai>")

    if not resend_key:
        logger.warning("DEV MODE — verification code for %s: %s", email, code)
        return

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            RESEND_API_URL,
            headers={"Authorization": f"Bearer {resend_key}"},
            json={
                "from": resend_from,
                "to": [email],
                "subject": f"Your crow verification code: {code}",
                "text": (
                    f"Your verification code is: {code}\n\n"
                    "It expires in 10 minutes. If you didn't request this, ignore this email."
                ),
            },
        )
        if resp.status_code >= 400:
            logger.error("Resend API error %d: %s", resp.status_code, resp.text)
            raise RuntimeError(f"Failed to send verification email: {resp.status_code}")
        logger.info("Verification email sent to %s", email)
