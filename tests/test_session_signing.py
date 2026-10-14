"""Session cookie signing: tampering invalidates the session."""
from __future__ import annotations

from app.auth.sessions import make_session_cookie, read_session_cookie


def test_round_trip() -> None:
    cookie = make_session_cookie(42)
    assert read_session_cookie(cookie) == 42


def test_tampered_cookie_rejected() -> None:
    cookie = make_session_cookie(42)
    parts = cookie.split(".")
    assert len(parts) == 3
    # 1. Tamper payload
    tampered_payload = f"{'b' if parts[0][0] != 'b' else 'c'}{parts[0][1:]}.{parts[1]}.{parts[2]}"
    assert read_session_cookie(tampered_payload) is None
    # 2. Tamper signature at index 0 (avoiding trailing base64 padding bits)
    tampered_sig = f"{parts[0]}.{parts[1]}.{'b' if parts[2][0] != 'b' else 'c'}{parts[2][1:]}"
    assert read_session_cookie(tampered_sig) is None


def test_random_garbage_rejected() -> None:
    assert read_session_cookie("not-a-real-cookie") is None
