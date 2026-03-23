"""API key generation and hashing."""

import hashlib
import secrets


def generate_api_key() -> tuple[str, str, str]:
    """Generate a new API key. Returns (full_key, key_hash, key_prefix)."""
    raw = secrets.token_urlsafe(32)
    full_key = f"crow_{raw}"
    key_hash = hash_api_key(full_key)
    key_prefix = full_key[:12]
    return full_key, key_hash, key_prefix


def hash_api_key(key: str) -> str:
    """SHA-256 hash of an API key."""
    return hashlib.sha256(key.encode()).hexdigest()
