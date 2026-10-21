"""INTERLOCK V6 — WP-10: predictable shutdown teardown (G-17).

Mission requirement (operations/predictability): the service must stop
deterministically — a stop/restart must release pooled database
connections instead of leaving sessions/files/locks held until process
kill.

Scope of this WP:
* lifespan shutdown hook that disposes the SQLAlchemy engine exactly once
  per application stop (verified with a spy, no real DB dependency in the
  unit test);
* a graceful-stop test through the real ``TestClient`` lifespan: the app
  serves while running, the shutdown hook fires exactly once on context
  exit, and a restart cycle (second lifespan) works again afterwards.

Explicitly BLOCKED (not simulated): multi-instance rolling restarts and
connection-drain timing under live Postgres load require infrastructure
this run is not authorized to install — recorded in the release gap
assessment, never faked here.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import create_app, lifespan


class _EngineStub:
    """Spy for the SQLAlchemy engine's dispose() at shutdown."""

    def __init__(self) -> None:
        self.dispose_calls = 0

    def dispose(self) -> None:
        self.dispose_calls += 1


async def test_lifespan_shutdown_disposes_database_engine(monkeypatch) -> None:
    """The lifespan's post-yield teardown must release the DB engine."""
    import app.main as app_main
    from app.infrastructure.persistence import database as database_module

    stub = _EngineStub()
    # init_db() binds to the real engine in production; this unit test
    # replaces both so no database is required.
    monkeypatch.setattr(app_main, "init_db", lambda: None)
    monkeypatch.setattr(database_module, "engine", stub)

    async with lifespan(FastAPI()):
        assert stub.dispose_calls == 0  # nothing torn down while running

    assert stub.dispose_calls == 1  # shutdown hook disposed the engine


def test_graceful_stop_disposes_engine_exactly_once() -> None:
    """Full TestClient lifespan: serve → stop → engine disposed once."""
    from sqlalchemy.engine import Engine

    calls: list[str] = []
    original_dispose = Engine.dispose

    def _spy(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        calls.append("dispose")
        return original_dispose(self, *args, **kwargs)

    Engine.dispose = _spy  # type: ignore[method-assign]
    try:
        application = create_app()
        with TestClient(application) as client:
            # While running the app serves requests and nothing is disposed.
            response = client.post("/api/v1/auth/login", json={})
            assert response.status_code == 422  # app is alive (validation)
            assert calls == []
        # Context exit ran the lifespan teardown exactly once.
        assert calls == ["dispose"]

        # Graceful stop → restart: releasing the engine must not wedge the
        # process; a second lifespan cycle serves again and, on its own
        # exit, disposes exactly once more.
        with TestClient(create_app()) as restarted:
            response = restarted.post("/api/v1/auth/login", json={})
            assert response.status_code == 422  # app serves after restart
        assert calls == ["dispose", "dispose"]
    finally:
        Engine.dispose = original_dispose  # type: ignore[method-assign]
