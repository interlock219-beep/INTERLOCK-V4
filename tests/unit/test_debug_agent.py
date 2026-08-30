from fastapi.testclient import TestClient
from sqlalchemy import literal, select


def test_debug_agent_create(client: TestClient) -> None:
    import asyncio
    from uuid import uuid4

    from app.domain.entities.user import User
    from app.infrastructure.config.settings import get_settings
    from app.infrastructure.persistence.database import SessionLocal
    from app.infrastructure.persistence.repositories.sqlalchemy_user_repository import (
        SQLAlchemyUserRepository,
    )
    from app.infrastructure.security.bcrypt_password_hasher import BcryptPasswordHasher
    from app.infrastructure.security.jwt_token_service import JWTTokenService

    settings = get_settings()
    session = SessionLocal()
    try:
        repo = SQLAlchemyUserRepository(session)
        user = User(
            id=uuid4(),
            email="debug@example.com",
            hashed_password=BcryptPasswordHasher(rounds=4).hash("Password123!"),
            is_active=True,
            created_at=__import__("datetime").datetime.now(tz=__import__("datetime").UTC),
            role="admin",
            tenant_id="tenant-a",
        )
        saved = asyncio.run(repo.save(user))
        token = JWTTokenService(
            secret_key=settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
            expire_minutes=settings.jwt_access_token_expire_minutes,
            clock_skew_seconds=settings.jwt_clock_skew_seconds,
        ).create_access_token(user_id=saved.id, email=saved.email)
        session.commit()
    finally:
        session.close()

    # Test direct query with select(literal(1))
    from app.infrastructure.persistence.models.agent_model import AgentModel
    from app.infrastructure.persistence.repositories.sqlalchemy_agent_repository import (
        SQLAlchemyAgentRepository,
    )

    s = SessionLocal()
    try:
        repo = SQLAlchemyAgentRepository(s)
        stmt = select(literal(1)).where(
            AgentModel.tenant_id == "tenant-a",
            AgentModel.agent_id == "agent-alpha",
        )
        _result = s.scalar(stmt)
    finally:
        s.close()

    _resp = client.post(
        "/api/v1/agents/",
        json={
            "agent_id": "agent-alpha",
            "name": "Agent Alpha",
            "agent_type": "service_agent",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

