"""CSRF tokens.

We issue a per-session token via the same signed cookie. State-changing
requests (POST/PUT/PATCH/DELETE) must include a ``csrf_token`` form
field or ``X-CSRF-Token`` header that matches.

The check is performed in a dependency that lives in
``app.routers.deps``; this module just issues and verifies.
"""
from __future__ import annotations

import hmac
import secrets

from .sessions import make_session_cookie

# CSRF tokens are not signed cookies: they are 32 random bytes
# hex-encoded, kept in the user's session and compared with constant
# time. The same value is also embedded in rendered forms.


def make_csrf_token() -> str:
    return secrets.token_hex(32)


def verify_csrf(expected: str | None, provided: str | None) -> bool:
    if not expected or not provided:
        return False
    return hmac.compare_digest(expected, provided)


__all__ = ["make_csrf_token", "verify_csrf", "make_session_cookie"]
