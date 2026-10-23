"""Session token helpers: raw token lives in an HttpOnly cookie, only its
SHA-256 hash is persisted."""

from __future__ import annotations

import hashlib
import secrets

SESSION_COOKIE = "aap_session"


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
