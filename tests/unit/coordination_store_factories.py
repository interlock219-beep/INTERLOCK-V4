"""Coordination-backend factories for V6 WP-3 tests.

Creates isolated SQL stores over a caller-supplied directory (own SQLite
file per store kind), so contract tests and multi-process drills never
touch the application database.  Child processes import this module
directly (repo root is on ``sys.path`` for ``python -c``), which is why
it must stay import-light and side-effect free apart from table creation
on the caller's own scratch database.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.infrastructure.persistence.database import Base
from app.infrastructure.persistence.models.coordination_models import (  # noqa: F401 - registers tables on Base.metadata
    PlanLeaseModel,
    QuotaCounterModel,
)

BACKEND_TIMEOUT_SECONDS = 60


class ManualClock:
    """Deterministic clock shared by contract tests (no sleep-based waits)."""

    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


def _session_factory(db_dir: Path, filename: str) -> sessionmaker[Any]:
    db_dir = Path(db_dir)
    db_dir.mkdir(parents=True, exist_ok=True)
    url = f"sqlite:///{(db_dir / filename).as_posix()}"
    engine = create_engine(
        url,
        connect_args={"timeout": BACKEND_TIMEOUT_SECONDS, "check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(
        bind=engine, autocommit=False, autoflush=False, expire_on_commit=False
    )


def make_sql_lease_store(
    db_dir: Path, clock: Callable[[], datetime] | None = None
) -> Any:
    from app.infrastructure.persistence.repositories.sqlalchemy_coordination_stores import (
        SQLPlanLeaseStore,
    )

    return SQLPlanLeaseStore(
        _session_factory(Path(db_dir), "plan_leases.db"), clock=clock
    )


def make_sql_quota_store(db_dir: Path) -> Any:
    from app.infrastructure.persistence.repositories.sqlalchemy_coordination_stores import (
        SQLQuotaCounterStore,
    )

    return SQLQuotaCounterStore(_session_factory(Path(db_dir), "quota_counters.db"))


_UTC_T0 = datetime(2026, 3, 1, tzinfo=UTC)
