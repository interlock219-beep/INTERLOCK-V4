import os
from collections.abc import Generator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

# Set test environment before application imports.
os.environ.setdefault(
    "JWT_SECRET_KEY",
    "test-secret-key-that-is-at-least-32-characters-long",
)
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("COMPLIANCE_SECRET_KEY", "test-compliance-secret-key")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_test")
os.environ.setdefault("AUTHORIZATION_REQUIRE_TENANT", "false")
os.environ.setdefault("AUTHORIZATION_DEFAULT_DENY", "false")

from app.infrastructure.config.settings import get_settings  # noqa: E402
from app.infrastructure.logging.audit_logger import LOG_PATH  # noqa: E402
from app.infrastructure.persistence.database import (  # noqa: E402
    Base,
    SessionLocal,
    engine,
    init_db,
)
from app.main import create_app  # noqa: E402
from app.presentation.api.dependencies.security import reset_security_dependencies  # noqa: E402
from app.presentation.api.middleware.rate_limit import reset_rate_limits  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> Generator[None, None, None]:
    get_settings.cache_clear()
    reset_security_dependencies()
    reset_rate_limits()
    yield
    get_settings.cache_clear()
    reset_security_dependencies()
    reset_rate_limits()


@pytest.fixture(autouse=True)
def _clear_audit_log() -> Generator[None, None, None]:
    if LOG_PATH.exists():
        LOG_PATH.unlink()
    yield


@pytest.fixture(autouse=True)
def _setup_database() -> Generator[None, None, None]:
    Base.metadata.drop_all(bind=engine)
    init_db()
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    application = create_app()
    with TestClient(application) as test_client:
        yield test_client


@pytest.fixture
def valid_password() -> str:
    return "SecurePass1!"


@pytest.fixture
def seed_plans(db_session: Session) -> None:
    from app.domain.entities.billing_entities import PlanTier
    from app.infrastructure.persistence.models import PlanModel

    existing = db_session.query(PlanModel).count()
    if existing > 0:
        return

    now = datetime.now(tz=UTC)
    plans = [
        PlanModel(
            id=uuid4(),
            name="Free",
            tier=PlanTier.FREE,
            price_monthly_cents=0,
            price_yearly_cents=0,
            currency="usd",
            features="{}",
            limits='{"intents_per_day": 100}',
            is_active=True,
            created_at=now,
            updated_at=now,
        ),
        PlanModel(
            id=uuid4(),
            name="Pro",
            tier=PlanTier.PRO,
            price_monthly_cents=4900,
            price_yearly_cents=47040,
            currency="usd",
            features="{}",
            limits='{"intents_per_day": 10000}',
            is_active=True,
            created_at=now,
            updated_at=now,
        ),
    ]
    for plan in plans:
        db_session.add(plan)
    db_session.commit()
