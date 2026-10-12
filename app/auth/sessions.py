"""Signed-cookie sessions.

We use ``itsdangerous`` URLSafeTimedSerializer with the app's
``SECRET_KEY``. The cookie payload is just the user id; everything
else (password hash, base currency, admin flag) is looked up from the
database on every request so changing the password invalidates
sessions in the natural way (the user record is re-fetched).
"""
from __future__ import annotations

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from ..config import get_settings

_MAX_AGE_SECONDS = 60 * 60 * 24 * 30  # 30 days


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().secret_key, salt="pocketledger-session")


def make_session_cookie(user_id: int) -> str:
    return _serializer().dumps({"uid": user_id})


def read_session_cookie(value: str) -> int | None:
    try:
        data = _serializer().loads(value, max_age=_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None
    uid = data.get("uid")
    if not isinstance(uid, int):
        return None
    return uid
