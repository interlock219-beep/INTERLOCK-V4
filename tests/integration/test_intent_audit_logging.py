import asyncio
import json

from fastapi.testclient import TestClient

from app.domain.entities.user import User
from app.infrastructure.config.settings import get_settings

# Read the path the app actually writes to. tests/conftest.py points the audit
# trail at a per-session temp file (TST-10: two runs must not share one trail),
# so a hardcoded logs/audit_trail.jsonl could never exist during the suite.
from app.infrastructure.logging.audit_logger import LOG_PATH as AUDIT_LOG_PATH
from app.infrastructure.persistence.database import SessionLocal
from app.infrastructure.persistence.repositories.sqlalchemy_user_repository import (
    SQLAlchemyUserRepository,
)
from app.infrastructure.security.bcrypt_password_hasher import BcryptPasswordHasher
from app.infrastructure.security.jwt_token_service import JWTTokenService


async def _create_user(email: str, role: str = "viewer") -> str:
    settings = get_settings()
    session = SessionLocal()
    try:
        repo = SQLAlchemyUserRepository(session)
        user = User(
            id=__import__("uuid").uuid4(),
            email=email,
            hashed_password=BcryptPasswordHasher(rounds=4).hash("Password123!"),
            is_active=True,
            created_at=__import__("datetime").datetime.now(tz=__import__("datetime").UTC),
            role=role,
            tenant_id="test-tenant",
        )
        saved = await repo.save(user)
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


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_intent_verification_audit_records_written(client: TestClient) -> None:
    if AUDIT_LOG_PATH.exists():
        AUDIT_LOG_PATH.unlink()

    token = asyncio.run(
        _create_user("audit-test@example.com")
    )

    response = client.post(
        "/api/v1/intent/verify",
        json={
            "user_prompt": "Search for user records",
            "agent_id": "agent-123",
            "reasoning_step": "Execute search",
            "proposed_tool": "search",
            "tool_arguments": {"query": "SELECT * FROM users LIMIT 10"},
        },
        headers=_auth_headers(token),
    )

    assert response.status_code == 200
    assert AUDIT_LOG_PATH.exists()

    with AUDIT_LOG_PATH.open("r", encoding="utf-8") as handle:
        lines = [line.strip() for line in handle if line.strip()]

    assert len(lines) >= 1
    record = json.loads(lines[-1])
    assert record["agent_id"] == "agent-123"
    assert record["proposed_tool"] == "search"
    assert record["verification_status"] == "PERMITTED"
    assert record["rejection_reason"] == ""
