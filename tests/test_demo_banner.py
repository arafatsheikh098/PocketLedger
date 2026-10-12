"""DEMO_MODE banner is rendered on every page when the flag is on."""
from __future__ import annotations

from fastapi.testclient import TestClient


def _login(client: TestClient) -> None:
    r = client.get("/auth/login")
    csrf = r.cookies.get("pocketledger_csrf")
    client.post(
        "/auth/login",
        data={"username": "alice", "password": "pw12345678", "csrf_token": csrf},
        follow_redirects=False,
    )


def _make_app(demo_mode: bool, monkeypatch):
    """Build a fresh app with the given demo_mode.

    The settings cache must be cleared because some routers read
    from ``get_settings()`` directly (and would otherwise return a
    cached value from a previous test). Pydantic-settings reads
    DEMO_MODE from the environment, so we set both the env var
    and the constructor argument.
    """
    from app import create_app
    from app.config import Settings, get_settings

    monkeypatch.setenv("DEMO_MODE", "true" if demo_mode else "false")
    monkeypatch.setenv("SEED_ON_START", "false")
    get_settings.cache_clear()
    settings = Settings(
        secret_key="x" * 32,
        database_url="sqlite:///:memory:",
        demo_mode=demo_mode,
        allow_registration=False,
        seed_on_start=False,
        app_env="development",
    )
    return create_app(settings)


def test_demo_banner_present_when_demo_mode_on(monkeypatch) -> None:
    app = _make_app(demo_mode=True, monkeypatch=monkeypatch)
    with TestClient(app) as c:
        r = c.get("/auth/login")
        assert r.status_code == 200
        assert "banner-demo" in r.text


def test_demo_banner_absent_when_demo_mode_off(monkeypatch) -> None:
    app = _make_app(demo_mode=False, monkeypatch=monkeypatch)
    with TestClient(app) as c:
        r = c.get("/auth/login")
        assert r.status_code == 200
        assert "banner-demo" not in r.text
