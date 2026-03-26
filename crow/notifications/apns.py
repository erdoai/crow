"""APNs push notification sender using JWT authentication."""

import json
import logging
import os
import time
from pathlib import Path

import httpx
import jwt

logger = logging.getLogger(__name__)

# APNs endpoints
APNS_PRODUCTION = "https://api.push.apple.com"
APNS_SANDBOX = "https://api.sandbox.push.apple.com"


def _load_apns_key() -> str | None:
    """Load APNs key from env var (contents) or file path."""
    key = os.environ.get("APNS_KEY")
    if key:
        return key
    key_path = os.environ.get("APNS_KEY_PATH")
    if key_path and Path(key_path).exists():
        return Path(key_path).read_text()
    return None


def _create_token() -> str | None:
    """Create a JWT token for APNs authentication."""
    key = _load_apns_key()
    key_id = os.environ.get("APNS_KEY_ID")
    team_id = os.environ.get("APNS_TEAM_ID")

    if not all([key, key_id, team_id]):
        return None

    headers = {"alg": "ES256", "kid": key_id}
    payload = {"iss": team_id, "iat": int(time.time())}
    return jwt.encode(payload, key, algorithm="ES256", headers=headers)


async def send_push(
    device_token: str,
    title: str,
    body: str,
    *,
    bundle_id: str | None = None,
    sandbox: bool = False,
) -> bool:
    """Send a push notification to an iOS device via APNs HTTP/2."""
    token = _create_token()
    if not token:
        logger.debug("APNs not configured — skipping push notification")
        return False

    app_bundle_id = bundle_id or os.environ.get("APNS_BUNDLE_ID", "ai.erdo.crow")
    base_url = APNS_SANDBOX if sandbox else APNS_PRODUCTION
    url = f"{base_url}/3/device/{device_token}"

    payload = {
        "aps": {
            "alert": {"title": title, "body": body},
            "sound": "default",
        }
    }

    try:
        async with httpx.AsyncClient(http2=True) as client:
            response = await client.post(
                url,
                content=json.dumps(payload),
                headers={
                    "authorization": f"bearer {token}",
                    "apns-topic": app_bundle_id,
                    "apns-push-type": "alert",
                    "content-type": "application/json",
                },
                timeout=10.0,
            )
            if response.status_code == 200:
                logger.debug("Push sent to %s", device_token[:8])
                return True
            else:
                logger.warning(
                    "APNs error %d: %s", response.status_code, response.text
                )
                return False
    except Exception:
        logger.exception("Failed to send push notification")
        return False


async def notify_user(
    db, user_id: str, title: str, body: str
) -> int:
    """Send push notification to all of a user's registered devices.

    Returns the number of successful sends.
    """
    tokens = await db.get_device_tokens_for_user(user_id)
    if not tokens:
        return 0

    sent = 0
    for tok in tokens:
        if tok["platform"] == "apns":
            ok = await send_push(tok["token"], title, body)
            if ok:
                sent += 1
    return sent
