"""Session cookie signing: tampering invalidates the session."""
from __future__ import annotations

from app.auth.sessions import make_session_cookie, read_session_cookie


def test_round_trip() -> None:
    cookie = make_session_cookie(42)
    assert read_session_cookie(cookie) == 42


def test_tampered_cookie_rejected() -> None:
    cookie = make_session_cookie(42)
    tampered = cookie[:-1] + ("A" if cookie[-1] != "A" else "B")
    assert read_session_cookie(tampered) is None


def test_random_garbage_rejected() -> None:
    assert read_session_cookie("not-a-real-cookie") is None
