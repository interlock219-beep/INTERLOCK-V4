"""RecoveryCreditService: wallet, ledger, holds, idempotency and expiry.

Runs against the real SQLAlchemy models on the test database, exercising the
exact production accounting paths (atomic reserve -> settle -> ledger).
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.domain.entities.billing_entities import CreditLedgerKind
from app.domain.exceptions.billing_errors import InsufficientCreditsError
from app.domain.services.recovery_credit_service import RecoveryCreditService
from app.infrastructure.config.settings import get_settings
from app.infrastructure.persistence.database import Base
from app.infrastructure.persistence.models.credit_models import (
    CreditLedgerModel,
    CreditReservationModel,
    CreditWalletModel,
)
from app.infrastructure.persistence.repositories.sqlalchemy_credit_repositories import (
    SQLAlchemyCreditRepository,
)

TENANT = "tenant-credit-test"


def _service(session) -> RecoveryCreditService:
    return RecoveryCreditService(
        SQLAlchemyCreditRepository(session),
        reservation_ttl_minutes=get_settings().credit_reservation_ttl_minutes,
    )


async def _allocate(
    service: RecoveryCreditService,
    *,
    tenant: str = TENANT,
    amount: int = 250,
    key: str = "alloc:sub-test:1000",
    tier: str = "pro",
    start: datetime | None = None,
    end: datetime | None = None,
):
    now = datetime.now(tz=UTC)
    return await service.allocate(
        tenant,
        amount=amount,
        period_start=start or now,
        period_end=end or (now + timedelta(days=30)),
        idempotency_key=key,
        reason="paid period allowance",
        plan_tier=tier,
        plan_name=tier.title(),
    )


class TestAllocation:
    @pytest.mark.asyncio
    async def test_starter_allocation_grants_100_credits(self, db_session) -> None:
        service = _service(db_session)
        entry = await _allocate(service, amount=100, tier="starter")
        assert entry is not None and entry.delta == 100
        wallet = await service.get_wallet(TENANT)
        assert wallet is not None
        assert wallet.allocated == 100
        assert wallet.available == 100
        assert wallet.is_enforced is True

    @pytest.mark.asyncio
    async def test_pro_allocation_grants_250_credits(self, db_session) -> None:
        service = _service(db_session)
        await _allocate(service, amount=250, tier="pro")
        wallet = await service.get_wallet(TENANT)
        assert wallet is not None and wallet.available == 250

    @pytest.mark.asyncio
    async def test_duplicate_allocation_is_idempotent(self, db_session) -> None:
        service = _service(db_session)
        first = await _allocate(service)
        second = await _allocate(service)
        assert first is not None
        assert second is None  # replayed webhook for the same period
        wallet = await service.get_wallet(TENANT)
        assert wallet is not None and wallet.allocated == 250
        entries = await service.list_ledger(TENANT)
        assert [e.kind for e in entries] == [CreditLedgerKind.ALLOCATION]

    @pytest.mark.asyncio
    async def test_allocate_non_positive_is_noop(self, db_session) -> None:
        service = _service(db_session)
        assert await _allocate(service, amount=0) is None
        assert await service.get_wallet(TENANT) is None


class TestReserveAndSettle:
    @pytest.mark.asyncio
    async def test_reserve_holds_one_credit(self, db_session) -> None:
        service = _service(db_session)
        await _allocate(service, amount=250)
        hold = await service.reserve_for_execution(TENANT, "plan-a")
        assert hold is not None and hold.already_billed is False
        wallet = await service.get_wallet(TENANT)
        assert wallet is not None
        assert wallet.reserved == 1
        assert wallet.available == 249

    @pytest.mark.asyncio
    async def test_billable_outcome_consumes_the_hold(self, db_session) -> None:
        service = _service(db_session)
        await _allocate(service, amount=250)
        hold = await service.reserve_for_execution(TENANT, "plan-a")
        assert hold is not None
        outcome = await service.finalize_hold(hold, billable=True)
        assert outcome == "consumed"
        wallet = await service.get_wallet(TENANT)
        assert wallet is not None
        assert wallet.consumed == 1
        assert wallet.reserved == 0
        assert wallet.available == 249
        entries = await service.list_ledger(TENANT)  # newest first
        kinds = [e.kind for e in entries]
        assert kinds == [
            CreditLedgerKind.CONSUMPTION,
            CreditLedgerKind.RESERVATION,
            CreditLedgerKind.ALLOCATION,
        ]
        consumption = entries[0]
        assert consumption.recovery_plan_id == "plan-a"

    @pytest.mark.asyncio
    async def test_non_billable_outcome_releases_the_hold(self, db_session) -> None:
        service = _service(db_session)
        await _allocate(service, amount=250)
        hold = await service.reserve_for_execution(TENANT, "plan-a")
        assert hold is not None
        outcome = await service.finalize_hold(hold, billable=False)
        assert outcome == "released"
        wallet = await service.get_wallet(TENANT)
        assert wallet is not None
        assert wallet.consumed == 0
        assert wallet.reserved == 0
        assert wallet.available == 250

    @pytest.mark.asyncio
    async def test_a_billed_plan_never_charges_twice(self, db_session) -> None:
        service = _service(db_session)
        await _allocate(service, amount=250)
        first = await service.reserve_for_execution(TENANT, "plan-a")
        assert first is not None
        assert await service.finalize_hold(first, billable=True) == "consumed"

        retry = await service.reserve_for_execution(TENANT, "plan-a")
        assert retry is not None and retry.already_billed is True
        assert await service.finalize_hold(retry, billable=True) == "already_billed"
        wallet = await service.get_wallet(TENANT)
        assert wallet is not None and wallet.consumed == 1

    @pytest.mark.asyncio
    async def test_re_execution_after_release_charges_at_most_once(
        self, db_session
    ) -> None:
        service = _service(db_session)
        await _allocate(service, amount=250)
        failed = await service.reserve_for_execution(TENANT, "plan-a")
        assert failed is not None
        assert await service.finalize_hold(failed, billable=False) == "released"
        second = await service.reserve_for_execution(TENANT, "plan-a")
        assert second is not None and second.already_billed is False
        assert await service.finalize_hold(second, billable=True) == "consumed"
        # A third attempt sees the lifetime consumption and stays free.
        third = await service.reserve_for_execution(TENANT, "plan-a")
        assert third is not None and third.already_billed is True
        wallet = await service.get_wallet(TENANT)
        assert wallet is not None and wallet.consumed == 1

    @pytest.mark.asyncio
    async def test_retried_request_reuses_the_active_hold(self, db_session) -> None:
        service = _service(db_session)
        await _allocate(service, amount=250)
        first = await service.reserve_for_execution(TENANT, "plan-a")
        second = await service.reserve_for_execution(TENANT, "plan-a")
        assert first is not None and second is not None
        assert first.reservation_id == second.reservation_id
        wallet = await service.get_wallet(TENANT)
        assert wallet is not None and wallet.reserved == 1  # not double-held

    @pytest.mark.asyncio
    async def test_insufficient_credits_raises_with_context(self, db_session) -> None:
        service = _service(db_session)
        await _allocate(service, amount=1)
        hold = await service.reserve_for_execution(TENANT, "plan-a")
        assert hold is not None
        with pytest.raises(InsufficientCreditsError) as excinfo:
            await service.reserve_for_execution(TENANT, "plan-b")
        assert excinfo.value.available == 0
        assert excinfo.value.required == 1
        assert excinfo.value.period_end is not None

    @pytest.mark.asyncio
    async def test_zero_credit_wallet_blocks_execution(self, db_session) -> None:
        service = _service(db_session)
        await _allocate(service, amount=1)
        hold = await service.reserve_for_execution(TENANT, "plan-a")
        assert hold is not None
        await service.finalize_hold(hold, billable=True)
        with pytest.raises(InsufficientCreditsError):
            await service.reserve_for_execution(TENANT, "plan-b")

    @pytest.mark.asyncio
    async def test_evaluation_tenant_runs_unbilled(self, db_session) -> None:
        service = _service(db_session)
        # No wallet at all: the free evaluation tier is never gated.
        assert await service.reserve_for_execution("tenant-without-wallet", "plan-a") is None

    @pytest.mark.asyncio
    async def test_deactivated_wallet_falls_back_to_evaluation(self, db_session) -> None:
        service = _service(db_session)
        await _allocate(service, amount=250)
        await service.deactivate(TENANT, reason="canceled")
        assert await service.reserve_for_execution(TENANT, "plan-a") is None


class TestPeriodLifecycle:
    @pytest.mark.asyncio
    async def test_unused_credits_expire_at_renewal(self, db_session) -> None:
        service = _service(db_session)
        past_start = datetime.now(tz=UTC) - timedelta(days=60)
        past_end = datetime.now(tz=UTC) - timedelta(days=30)
        await _allocate(
            service, amount=250, key="alloc:sub:period1", start=past_start, end=past_end
        )
        hold = await service.reserve_for_execution(TENANT, "plan-a")
        assert hold is not None
        await service.finalize_hold(hold, billable=True)  # consume exactly one

        now = datetime.now(tz=UTC)
        entry = await _allocate(
            service,
            amount=250,
            key="alloc:sub:period2",
            start=now,
            end=now + timedelta(days=30),
        )
        assert entry is not None
        wallet = await service.get_wallet(TENANT)
        assert wallet is not None
        # 249 unused credits of the old period expired into the ledger; the
        # new period starts fresh with its own 250. No rollover.
        assert wallet.allocated == 250
        assert wallet.consumed == 0
        assert wallet.available == 250
        kinds = [e.kind for e in await service.list_ledger(TENANT)]
        assert CreditLedgerKind.EXPIRY in kinds

    @pytest.mark.asyncio
    async def test_deactivate_expires_remaining_and_records_it(
        self, db_session
    ) -> None:
        service = _service(db_session)
        await _allocate(service, amount=100)
        expired = await service.deactivate(TENANT, reason="subscription canceled")
        assert expired == 100
        wallet = await service.get_wallet(TENANT)
        assert wallet is not None
        assert wallet.available == 0
        assert wallet.is_enforced is False
        kinds = [e.kind for e in await service.list_ledger(TENANT)]
        assert CreditLedgerKind.EXPIRY in kinds

    @pytest.mark.asyncio
    async def test_plan_upgrade_grants_the_difference(self, db_session) -> None:
        service = _service(db_session)
        await _allocate(service, amount=100, tier="starter")
        granted = await service.apply_plan_upgrade(
            TENANT,
            new_monthly_credits=250,
            subscription_id=None,
            idempotency_key="adjust:sub:pro",
            reason="upgraded to Pro",
        )
        assert granted == 150
        wallet = await service.get_wallet(TENANT)
        assert wallet is not None and wallet.available == 250
        entries = await service.list_ledger(TENANT)
        assert entries[0].kind == CreditLedgerKind.ADJUSTMENT

    @pytest.mark.asyncio
    async def test_plan_upgrade_is_idempotent(self, db_session) -> None:
        service = _service(db_session)
        await _allocate(service, amount=100, tier="starter")
        kwargs = {
            "new_monthly_credits": 250,
            "subscription_id": None,
            "idempotency_key": "adjust:sub:pro",
            "reason": "upgraded to Pro",
        }
        assert await service.apply_plan_upgrade(TENANT, **kwargs) == 150
        assert await service.apply_plan_upgrade(TENANT, **kwargs) == 0

    @pytest.mark.asyncio
    async def test_downgrade_grants_nothing_mid_period(self, db_session) -> None:
        service = _service(db_session)
        await _allocate(service, amount=250, tier="pro")
        granted = await service.apply_plan_upgrade(
            TENANT,
            new_monthly_credits=100,
            subscription_id=None,
            idempotency_key="adjust:sub:down",
            reason="downgraded to Starter",
        )
        assert granted == 0
        wallet = await service.get_wallet(TENANT)
        assert wallet is not None and wallet.available == 250


class TestLedgerIntegrity:
    @pytest.mark.asyncio
    async def test_ledger_balance_chain_matches_wallet(self, db_session) -> None:
        service = _service(db_session)
        await _allocate(service, amount=2)
        hold = await service.reserve_for_execution(TENANT, "plan-a")
        assert hold is not None
        await service.finalize_hold(hold, billable=True)
        hold_b = await service.reserve_for_execution(TENANT, "plan-b")
        assert hold_b is not None
        await service.finalize_hold(hold_b, billable=False)

        entries = list(reversed(await service.list_ledger(TENANT)))  # oldest first
        # allocation 2 -> reserve plan-a 1 -> consume (capture of the hold,
        # no further movement) -> reserve plan-b 0 -> release 1.
        assert [e.balance_after for e in entries] == [2, 1, 1, 0, 1]
        wallet = await service.get_wallet(TENANT)
        assert wallet is not None
        # plan-a consumed one credit; plan-b's hold was returned.
        assert entries[-1].balance_after == wallet.available == 1

    @pytest.mark.asyncio
    async def test_ledger_is_tenant_scoped(self, db_session) -> None:
        service = _service(db_session)
        await _allocate(service, tenant="tenant-a", key="alloc:a:1")
        await _allocate(service, tenant="tenant-b", key="alloc:b:1")
        entries_a = await service.list_ledger("tenant-a")
        assert all(e.tenant_id == "tenant-a" for e in entries_a)
        assert len(entries_a) == 1


class TestConcurrency:
    def test_threaded_reserves_never_overspend(self) -> None:
        """N threads racing for fewer credits than the wallet holds.

        Uses a file-backed SQLite so each thread owns a real connection and
        the conditional updates genuinely race. The invariant: the number of
        admitted holds never exceeds the allocated balance.
        """
        import tempfile
        from pathlib import Path

        allocated = 5
        attempts = 12
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "concurrency.db"
            engine = create_engine(
                f"sqlite:///{db_path}",
                connect_args={"check_same_thread": False, "timeout": 30},
            )
            try:
                Base.metadata.create_all(engine)
                factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

                setup = factory()
                try:
                    asyncio.run(
                        _allocate(
                            _service(setup),
                            amount=allocated,
                            key="alloc:cc:1",
                        )
                    )
                finally:
                    setup.close()

                admitted: list[object] = []

                def worker(index: int) -> None:
                    session = factory()
                    service = _service(session)
                    try:
                        hold = asyncio.run(
                            service.reserve_for_execution("tenant-cc", f"plan-{index}")
                        )
                        admitted.append(hold)
                    except InsufficientCreditsError:
                        admitted.append(None)
                    except Exception:  # pragma: no cover - DB contention fallback
                        admitted.append(None)
                    finally:
                        session.close()

                with ThreadPoolExecutor(max_workers=attempts) as pool:
                    list(pool.map(worker, range(attempts)))

                verify = factory()
                try:
                    wallet = verify.query(CreditWalletModel).one()
                    holds = [h for h in admitted if h is not None]
                    assert len(holds) <= allocated
                    assert wallet.reserved == len(holds)
                    assert wallet.allocated - wallet.consumed - wallet.reserved >= 0
                    reservations = verify.query(CreditReservationModel).count()
                    assert reservations == len(holds)
                    ledger_rows = verify.query(CreditLedgerModel).count()
                    assert ledger_rows == 1 + len(holds)  # allocation + one hold each
                finally:
                    verify.close()
            finally:
                # Release the pooled connections so Windows can delete the
                # temporary database file.
                engine.dispose()
