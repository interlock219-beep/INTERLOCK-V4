"""Real containment verification against live TestClient server."""
from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app.domain.entities.user import User
from app.infrastructure.config.settings import get_settings
from app.infrastructure.persistence.database import SessionLocal
from app.infrastructure.persistence.repositories.sqlalchemy_user_repository import (
    SQLAlchemyUserRepository,
)
from app.infrastructure.security.bcrypt_password_hasher import BcryptPasswordHasher
from app.infrastructure.security.jwt_token_service import JWTTokenService
from sdk.workspace_protection.path_security import WorkspacePathSecurity
from sdk.workspace_protection.protected_tools import ProtectedFilesystemTools


def _sha256(path: Path) -> str:
    if not path.exists():
        return ""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _make_admin_token(email: str) -> str:
    settings = get_settings()
    session = SessionLocal()
    try:
        repo = SQLAlchemyUserRepository(session)
        user = User(
            id=uuid.uuid4(),
            email=email,
            hashed_password=BcryptPasswordHasher(rounds=4).hash("SecurePass1!"),
            is_active=True,
            created_at=datetime.now(tz=UTC),
            role="admin",
            tenant_id="tenant-containment",
        )
        import asyncio

        saved = asyncio.run(repo.save(user))
        token = JWTTokenService(
            secret_key=settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
            expire_minutes=settings.jwt_access_token_expire_minutes,
            clock_skew_seconds=settings.jwt_clock_skew_seconds,
        ).create_access_token(user_id=saved.id, email=saved.email)
        session.commit()
        return token
    finally:
        session.close()


def _create_agent(client: TestClient, token: str, agent_id: str) -> None:
    resp = client.post(
        "/api/v1/agents",
        json={
        "agent_id": agent_id,
        "name": agent_id,
        "description": "",
        "agent_type": "tool_agent",
        "environment": "test",
    },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code in (200, 201), resp.text


def _create_session(client: TestClient, token: str, agent_id: str) -> str:
    resp = client.post(
        "/api/v1/agent-sessions",
        json={"agent_id": agent_id, "intent_id": "intent-1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["session_id"]


def _freeze_session(client: TestClient, token: str, session_id: str) -> dict:
    resp = client.post(
        f"/api/v1/agent-sessions/{session_id}/freeze",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _kill_agent(client: TestClient, token: str, agent_id: str) -> dict:
    resp = client.post(
        f"/api/v1/agents/{agent_id}/kill",
        json={"reason": "containment test"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _post_via_client(client: TestClient, token: str, path: str, payload: dict) -> dict:
    resp = client.post(path, json=payload, headers={"Authorization": f"Bearer {token}"})
    if resp.status_code >= 400:
        return {"status_code": resp.status_code, "error": resp.text}
    result = {"status_code": resp.status_code}
    if resp.content:
        result.update(resp.json())
    return result


def test_frozen_session_blocks_new_mutation() -> None:
    from app.main import create_app

    app = create_app()
    client = TestClient(app)
    email = f"freeze-{uuid.uuid4().hex[:8]}@test.com"
    token = _make_admin_token(email)
    agent_id = f"agent-freeze-{uuid.uuid4().hex[:8]}"
    _create_agent(client, token, agent_id)
    session_id = _create_session(client, token, agent_id)

    workspace = Path("tmp_containment_test")
    workspace.mkdir(exist_ok=True)
    target = workspace / "frozen_blocked.txt"
    if target.exists():
        target.unlink()

    _freeze_session(client, token, session_id)

    path_security = WorkspacePathSecurity(workspace)
    tools = ProtectedFilesystemTools(
        path_security=path_security,
        gateway_url="http://test",
        auth_token=token,
        http_client=lambda method, path, payload: _post_via_client(client, token, path, payload),
    )

    raised = False
    try:
        tools.write_file(
            path=target,
            content="This should be blocked",
            agent_id=agent_id,
            session_id=session_id,
            correlation_id="corr-freeze",
        )
    except Exception:
        raised = True

    assert raised, "FROZEN session mutation did not raise!"
    assert not target.exists(), "FROZEN session mutation was NOT blocked!"


def test_revoked_agent_blocks_new_mutation() -> None:
    from app.main import create_app

    app = create_app()
    client = TestClient(app)
    email = f"kill-{uuid.uuid4().hex[:8]}@test.com"
    token = _make_admin_token(email)
    agent_id = f"agent-kill-{uuid.uuid4().hex[:8]}"
    _create_agent(client, token, agent_id)
    session_id = _create_session(client, token, agent_id)

    workspace = Path("tmp_containment_test2")
    workspace.mkdir(exist_ok=True)
    target = workspace / "kill_blocked.txt"
    if target.exists():
        target.unlink()

    _kill_agent(client, token, agent_id)

    path_security = WorkspacePathSecurity(workspace)
    tools = ProtectedFilesystemTools(
        path_security=path_security,
        gateway_url="http://test",
        auth_token=token,
        http_client=lambda method, path, payload: _post_via_client(client, token, path, payload),
    )

    raised = False
    try:
        tools.write_file(
            path=target,
            content="This should be blocked",
            agent_id=agent_id,
            session_id=session_id,
            correlation_id="corr-kill",
        )
    except Exception:
        raised = True

    assert raised, "REVOKED agent mutation did not raise!"
    assert not target.exists(), "REVOKED agent mutation was NOT blocked!"


def test_quarantined_agent_blocks_new_mutation() -> None:
    from app.main import create_app

    app = create_app()
    client = TestClient(app)
    email = f"quarantine-{uuid.uuid4().hex[:8]}@test.com"
    token = _make_admin_token(email)
    agent_id = f"agent-quar-{uuid.uuid4().hex[:8]}"
    _create_agent(client, token, agent_id)
    session_id = _create_session(client, token, agent_id)

    resp = client.post(
        "/api/v1/containment",
        json={"target_agent_id": agent_id, "mode": "quarantine", "reason": "test"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code in (200, 201), resp.text

    workspace = Path("tmp_containment_test3")
    workspace.mkdir(exist_ok=True)
    target = workspace / "quarantine_blocked.txt"
    if target.exists():
        target.unlink()

    path_security = WorkspacePathSecurity(workspace)
    tools = ProtectedFilesystemTools(
        path_security=path_security,
        gateway_url="http://test",
        auth_token=token,
        http_client=lambda method, path, payload: _post_via_client(client, token, path, payload),
    )

    raised = False
    try:
        tools.write_file(
            path=target,
            content="This should be blocked",
            agent_id=agent_id,
            session_id=session_id,
            correlation_id="corr-quarantine",
        )
    except Exception:
        raised = True

    assert raised, "QUARANTINED agent mutation did not raise!"
    assert not target.exists(), "QUARANTINED agent mutation was NOT blocked!"


if __name__ == "__main__":
    test_frozen_session_blocks_new_mutation()
    test_revoked_agent_blocks_new_mutation()
    test_quarantined_agent_blocks_new_mutation()
