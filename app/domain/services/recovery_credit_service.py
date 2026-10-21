"""Recovery-credit domain service: wallet, ledger and execution holds.

Billable-recovery policy (the exact contract this service enforces):

* One **recovery plan execution** that reaches the engine's billable point --
  ``status == "completed"`` **and** ``verification_status ==
  "executed_and_verified"`` -- consumes **one** credit.
* A plan consumes **at most one credit for its lifetime**, no matter how many
  times it is executed or resumed (ledger key ``consume:{tenant}:{plan}``).
* Previews/simulations never reach this service; failed, stopped, partial and
  unverified runs consume nothing (their hold is released). Partial outcomes
  are therefore **not billed**.
* Before an execution, one credit is *reserved* atomically (conditional check
  + unique ledger key); the hold is converted to a consumption or released
  according to the verified outcome, so concurrent requests can never spend
  more credits than the wallet holds.
* Tenants that have never been allocated credits (no wallet) run in
  **evaluation mode**: executions proceed unbilled, exactly as before billing
  existed. Enforcement only applies to tenants with an allocated wallet
  (``is_enforced``).

Credits are server-controlled: every mutation happens here, inside the
repository transaction, with append-only ledger entries and idempotency keys.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.domain.entities.billing_entities import (
    CreditLedgerEntry,
    CreditLedgerKind,
    CreditReservation,
    CreditReservationStatus,
    CreditWallet,
)
from app.domain.exceptions.billing_errors import (
    DuplicateCreditOperationError,
    InsufficientCreditsError,
)
from app.domain.repositories.credit_repositories import CreditRepository

DEFAULT_RESERVATION_TTL_MINUTES = 60


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _as_utc(value: datetime) -> datetime:
    """Normalize persisted datetimes for comparisons.

    SQLite (and the test database) return naive datetimes even for
    timezone-aware columns; treat naive values as UTC so comparisons never
    mix offset-aware and offset-naive values.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class CreditHold:
    """Context for one in-flight billable execution."""

    tenant_id: str
    recovery_plan_id: str
    reservation_id: UUID
    already_billed: bool = False


@dataclass(frozen=True, slots=True)
class CreditSummary:
    """Read model for the billing dashboard."""

    tenant_id: str
    has_wallet: bool
    enforced: bool
    plan_tier: str
    plan_name: str
    allocated: int
    consumed: int
    reserved: int
    available: int
    period_start: datetime | None
    period_end: datetime | None
    subscription_id: UUID | None


class RecoveryCreditService:
    """Server-side authority over recovery-credit balances."""

    def __init__(
        self,
        repository: CreditRepository,
        *,
        reservation_ttl_minutes: int = DEFAULT_RESERVATION_TTL_MINUTES,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repo = repository
        self._ttl = reservation_ttl_minutes
        self._clock = clock or _now

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    async def get_wallet(self, tenant_id: str) -> CreditWallet | None:
        return await self._repo.get_wallet(tenant_id)

    async def summary(self, tenant_id: str) -> CreditSummary:
        wallet = await self._repo.get_wallet(tenant_id)
        if wallet is None:
            return CreditSummary(
                tenant_id=tenant_id,
                has_wallet=False,
                enforced=False,
                plan_tier="",
                plan_name="",
                allocated=0,
                consumed=0,
                reserved=0,
                available=0,
                period_start=None,
                period_end=None,
                subscription_id=None,
            )
        return CreditSummary(
            tenant_id=wallet.tenant_id,
            has_wallet=True,
            enforced=wallet.is_enforced,
            plan_tier=wallet.plan_tier,
            plan_name=wallet.plan_name,
            allocated=wallet.allocated,
            consumed=wallet.consumed,
            reserved=wallet.reserved,
            available=wallet.available,
            period_start=wallet.period_start,
            period_end=wallet.period_end,
            subscription_id=wallet.subscription_id,
        )

    async def list_ledger(
        self, tenant_id: str, *, limit: int = 50, offset: int = 0
    ) -> list[CreditLedgerEntry]:
        return await self._repo.list_ledger(tenant_id, limit=limit, offset=offset)

    # ------------------------------------------------------------------
    # Allocation (verified payments only -- never a frontend redirect)
    # ------------------------------------------------------------------
    async def allocate(
        self,
        tenant_id: str,
        *,
        amount: int,
        period_start: datetime,
        period_end: datetime,
        idempotency_key: str,
        reason: str,
        subscription_id: UUID | None = None,
        plan_tier: str = "",
        plan_name: str = "",
    ) -> CreditLedgerEntry | None:
        """Grant ``amount`` credits for a paid billing period.

        Idempotent: an allocation whose key is already in the ledger is a
        no-op (returns None), so duplicate ``invoice.paid`` webhooks can
        never double-grant. When the wallet's previous period has ended,
        the unused remainder expires first (documented no-rollover policy)
        before the new allowance is granted.
        """
        if amount <= 0:
            return None
        existing = await self._repo.get_ledger_entry_by_key(idempotency_key)
        if existing is not None:
            return None

        now = self._clock()
        wallet = await self._repo.get_wallet(tenant_id)
        expiry_entry: CreditLedgerEntry | None = None
        if wallet is None:
            wallet = CreditWallet(
                id=uuid4(),
                tenant_id=tenant_id,
                allocated=0,
                consumed=0,
                reserved=0,
                period_start=period_start,
                period_end=period_end,
                is_enforced=True,
                plan_tier=plan_tier,
                plan_name=plan_name,
                subscription_id=subscription_id,
                created_at=now,
                updated_at=now,
            )
        else:
            await self._sweep_expired_reservations(wallet.tenant_id, commit=False)
            wallet = await self._repo.get_wallet(tenant_id) or wallet
            # Rollover trigger: the wallet's period has ended (lazy expiry),
            # OR the incoming allocation belongs to a NEW period (renewal
            # invoices arrive at/after the previous period's end -- wall
            # clock alone is not reliable here). The previous period's
            # unused remainder expires into the ledger and the period
            # counters reset before the new allowance is granted.
            new_period = (
                wallet.period_end is not None
                and _as_utc(period_start) >= _as_utc(wallet.period_end)
            )
            period_ended = (
                wallet.period_end is not None and _as_utc(wallet.period_end) <= now
            )
            if period_ended or new_period:
                wallet, expiry_entry = self._expire_remaining_locked(wallet, now)
            wallet = CreditWallet(
                id=wallet.id,
                tenant_id=wallet.tenant_id,
                allocated=wallet.allocated,
                consumed=wallet.consumed,
                reserved=wallet.reserved,
                period_start=period_start,
                period_end=period_end,
                is_enforced=True,
                plan_tier=plan_tier or wallet.plan_tier,
                plan_name=plan_name or wallet.plan_name,
                subscription_id=subscription_id or wallet.subscription_id,
                provider_subscription_id=wallet.provider_subscription_id,
                created_at=wallet.created_at,
                updated_at=now,
            )

        wallet = CreditWallet(
            id=wallet.id,
            tenant_id=wallet.tenant_id,
            allocated=wallet.allocated + amount,
            consumed=wallet.consumed,
            reserved=wallet.reserved,
            period_start=wallet.period_start,
            period_end=wallet.period_end,
            is_enforced=wallet.is_enforced,
            plan_tier=wallet.plan_tier,
            plan_name=wallet.plan_name,
            subscription_id=wallet.subscription_id,
            provider_subscription_id=wallet.provider_subscription_id,
            created_at=wallet.created_at,
            updated_at=now,
        )
        entry = self._entry(
            wallet,
            kind=CreditLedgerKind.ALLOCATION,
            delta=amount,
            reason=reason,
            idempotency_key=idempotency_key,
            subscription_id=subscription_id,
        )
        await self._repo.save_wallet(wallet)
        if expiry_entry is not None and (
            await self._repo.get_ledger_entry_by_key(expiry_entry.idempotency_key)
        ) is None:
            await self._repo.add_ledger_entry(expiry_entry)
        await self._repo.add_ledger_entry(entry)
        await self._repo.commit()
        return entry

    async def attach_subscription(
        self,
        tenant_id: str,
        *,
        subscription_id: UUID | None,
        provider_subscription_id: str | None,
        plan_tier: str,
        plan_name: str,
    ) -> None:
        """Record the wallet's subscription linkage (create wallet if new)."""
        now = self._clock()
        wallet = await self._repo.get_wallet(tenant_id)
        if wallet is None:
            wallet = CreditWallet(
                id=uuid4(),
                tenant_id=tenant_id,
                allocated=0,
                consumed=0,
                reserved=0,
                period_start=now,
                period_end=now,
                is_enforced=False,
                plan_tier=plan_tier,
                plan_name=plan_name,
                subscription_id=subscription_id,
                provider_subscription_id=provider_subscription_id,
                created_at=now,
                updated_at=now,
            )
        else:
            wallet = CreditWallet(
                id=wallet.id,
                tenant_id=wallet.tenant_id,
                allocated=wallet.allocated,
                consumed=wallet.consumed,
                reserved=wallet.reserved,
                period_start=wallet.period_start,
                period_end=wallet.period_end,
                is_enforced=wallet.is_enforced,
                plan_tier=plan_tier or wallet.plan_tier,
                plan_name=plan_name or wallet.plan_name,
                subscription_id=subscription_id or wallet.subscription_id,
                provider_subscription_id=provider_subscription_id
                or wallet.provider_subscription_id,
                created_at=wallet.created_at,
                updated_at=now,
            )
        await self._repo.save_wallet(wallet)
        await self._repo.commit()

    # ------------------------------------------------------------------
    # Enforcement around an execution
    # ------------------------------------------------------------------
    async def reserve_for_execution(
        self, tenant_id: str, recovery_plan_id: str
    ) -> CreditHold | None:
        """Atomically hold one credit before a billable execution.

        Returns None for tenants in evaluation mode (no wallet) -- their
        executions are not billed. Raises :class:`InsufficientCreditsError`
        when an enforced wallet has no credits left. Re-entrant: a retried
        request for the same plan reuses the active hold, and a plan that
        was already billed returns ``already_billed=True`` so the re-run
        charges nothing.
        """
        wallet = await self._repo.get_wallet(tenant_id)
        if wallet is None or not wallet.is_enforced:
            await self._repo.commit()
            return None

        if await self._repo.was_plan_consumed(tenant_id, recovery_plan_id):
            await self._repo.commit()
            return CreditHold(
                tenant_id=tenant_id,
                recovery_plan_id=recovery_plan_id,
                reservation_id=uuid4(),
                already_billed=True,
            )

        active = await self._repo.get_active_reservation(tenant_id, recovery_plan_id)
        if active is not None:
            await self._repo.commit()
            return CreditHold(
                tenant_id=tenant_id,
                recovery_plan_id=recovery_plan_id,
                reservation_id=active.id,
                already_billed=False,
            )

        await self._sweep_expired_reservations(tenant_id, commit=True)
        wallet = await self._repo.get_wallet(tenant_id)
        if wallet is None or not wallet.is_enforced:
            await self._repo.commit()
            return None
        if wallet.available < 1:
            await self._repo.commit()
            raise InsufficientCreditsError(
                tenant_id=tenant_id,
                available=wallet.available,
                required=1,
                period_end=wallet.period_end,
            )

        now = self._clock()
        reservation = CreditReservation(
            id=uuid4(),
            tenant_id=tenant_id,
            recovery_plan_id=recovery_plan_id,
            status=CreditReservationStatus.ACTIVE,
            expires_at=now + timedelta(minutes=self._ttl),
            created_at=now,
        )
        wallet = CreditWallet(
            id=wallet.id,
            tenant_id=wallet.tenant_id,
            allocated=wallet.allocated,
            consumed=wallet.consumed,
            reserved=wallet.reserved + 1,
            period_start=wallet.period_start,
            period_end=wallet.period_end,
            is_enforced=wallet.is_enforced,
            plan_tier=wallet.plan_tier,
            plan_name=wallet.plan_name,
            subscription_id=wallet.subscription_id,
            provider_subscription_id=wallet.provider_subscription_id,
            created_at=wallet.created_at,
            updated_at=now,
        )
        entry = self._entry(
            wallet,
            kind=CreditLedgerKind.RESERVATION,
            delta=-1,
            reason="hold placed before recovery execution",
            idempotency_key=f"reserve:{reservation.id}",
        )
        await self._repo.save_wallet(wallet)
        await self._repo.save_reservation(reservation)
        await self._repo.add_ledger_entry(entry)
        await self._repo.commit()
        return CreditHold(
            tenant_id=tenant_id,
            recovery_plan_id=recovery_plan_id,
            reservation_id=reservation.id,
            already_billed=False,
        )

    async def finalize_hold(self, hold: CreditHold, *, billable: bool) -> str:
        """Settle a hold from the engine's verified outcome.

        Returns ``"consumed"``, ``"released"``, ``"already_billed"`` or
        ``"noop"`` (hold was already settled/expired -- reconciled by the
        sweep). Only ``billable=True`` (completed **and** verified) ever
        charges a credit, and only once per plan.
        """
        if hold.already_billed:
            return "already_billed"

        wallet = await self._repo.get_wallet(hold.tenant_id)
        if wallet is None:
            await self._repo.commit()
            return "noop"
        reservation = await self._repo.get_reservation(hold.reservation_id)
        if reservation is None or reservation.status is not CreditReservationStatus.ACTIVE:
            await self._repo.commit()
            return "noop"

        now = self._clock()
        if billable and not await self._repo.was_plan_consumed(
            hold.tenant_id, hold.recovery_plan_id
        ):
            wallet, reservation, entry, outcome = self._settle_consumption(
                wallet, reservation, now
            )
        else:
            # Not billable, or a concurrent finalize already charged this
            # plan: settle the hold as a release so the reserved counter
            # stays honest and nothing is double-charged.
            wallet, reservation, entry, outcome = self._settle_release(
                wallet, reservation, now
            )

        try:
            await self._repo.save_wallet(wallet)
            await self._repo.save_reservation(reservation)
            await self._repo.add_ledger_entry(entry)
            await self._repo.commit()
            return outcome
        except DuplicateCreditOperationError:
            # Another request won the race to record this ledger key (e.g. a
            # concurrent finalize charged the plan first). The failed insert
            # rolled the session back, so the hold is ACTIVE again: settle it
            # as a release. Either way the plan is charged at most once.
            fresh_wallet = await self._repo.get_wallet(hold.tenant_id)
            fresh_reservation = await self._repo.get_reservation(hold.reservation_id)
            if (
                fresh_wallet is not None
                and fresh_reservation is not None
                and fresh_reservation.status is CreditReservationStatus.ACTIVE
            ):
                released_wallet, settled, release_entry, _ = self._settle_release(
                    fresh_wallet, fresh_reservation, now
                )
                await self._repo.save_wallet(released_wallet)
                await self._repo.save_reservation(settled)
                try:
                    await self._repo.add_ledger_entry(release_entry)
                except DuplicateCreditOperationError:
                    await self._repo.rollback()
                await self._repo.commit()
            return "already_billed"

    # ------------------------------------------------------------------
    # Period lifecycle: expiry, upgrade, cancellation
    # ------------------------------------------------------------------
    async def expire_remaining(self, tenant_id: str, *, reason: str) -> int:
        """Expire unused credits (end of paid period / cancellation)."""
        now = self._clock()
        wallet = await self._repo.get_wallet(tenant_id)
        if wallet is None:
            await self._repo.commit()
            return 0
        await self._sweep_expired_reservations(tenant_id, commit=False)
        wallet = await self._repo.get_wallet(tenant_id) or wallet
        wallet, entry = self._expire_remaining_locked(wallet, now, reason=reason)
        expired = -entry.delta if entry is not None else 0
        if entry is not None:
            await self._repo.save_wallet(wallet)
            if (await self._repo.get_ledger_entry_by_key(entry.idempotency_key)) is None:
                await self._repo.add_ledger_entry(entry)
        await self._repo.commit()
        return expired

    async def deactivate(self, tenant_id: str, *, reason: str) -> int:
        """Cancellation: expire remaining credits and stop enforcement.

        After deactivation the tenant falls back to evaluation mode (the
        product's free tier), so recoveries keep working without credits --
        but nothing already paid is silently revoked without a ledger entry.
        """
        expired = await self.expire_remaining(tenant_id, reason=reason)
        wallet = await self._repo.get_wallet(tenant_id)
        if wallet is not None and wallet.is_enforced:
            wallet = CreditWallet(
                id=wallet.id,
                tenant_id=wallet.tenant_id,
                allocated=wallet.allocated,
                consumed=wallet.consumed,
                reserved=wallet.reserved,
                period_start=wallet.period_start,
                period_end=wallet.period_end,
                is_enforced=False,
                plan_tier=wallet.plan_tier,
                plan_name=wallet.plan_name,
                subscription_id=wallet.subscription_id,
                provider_subscription_id=wallet.provider_subscription_id,
                created_at=wallet.created_at,
                updated_at=self._clock(),
            )
            await self._repo.save_wallet(wallet)
            await self._repo.commit()
        return expired

    async def apply_plan_upgrade(
        self,
        tenant_id: str,
        *,
        new_monthly_credits: int,
        subscription_id: UUID | None,
        idempotency_key: str,
        reason: str,
    ) -> int:
        """Grant the allowance difference when a tenant upgrades mid-period.

        Downgrades are deliberately **not** applied mid-period: the current
        allowance stands until the period ends, then the new plan's allowance
        applies at the next renewal (documented policy).
        """
        if new_monthly_credits <= 0:
            return 0
        if await self._repo.get_ledger_entry_by_key(idempotency_key) is not None:
            return 0
        now = self._clock()
        wallet = await self._repo.get_wallet(tenant_id)
        if wallet is None or not wallet.is_enforced:
            await self._repo.commit()
            return 0
        difference = new_monthly_credits - wallet.allocated
        if difference <= 0:
            await self._repo.commit()
            return 0
        wallet = CreditWallet(
            id=wallet.id,
            tenant_id=wallet.tenant_id,
            allocated=wallet.allocated + difference,
            consumed=wallet.consumed,
            reserved=wallet.reserved,
            period_start=wallet.period_start,
            period_end=wallet.period_end,
            is_enforced=wallet.is_enforced,
            plan_tier=wallet.plan_tier,
            plan_name=wallet.plan_name,
            subscription_id=wallet.subscription_id or subscription_id,
            provider_subscription_id=wallet.provider_subscription_id,
            created_at=wallet.created_at,
            updated_at=now,
        )
        entry = self._entry(
            wallet,
            kind=CreditLedgerKind.ADJUSTMENT,
            delta=difference,
            reason=reason,
            idempotency_key=idempotency_key,
            subscription_id=subscription_id,
        )
        await self._repo.save_wallet(wallet)
        await self._repo.add_ledger_entry(entry)
        await self._repo.commit()
        return difference

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    @staticmethod
    def _entry(
        wallet: CreditWallet,
        *,
        kind: CreditLedgerKind,
        delta: int,
        reason: str,
        idempotency_key: str,
        subscription_id: UUID | None = None,
        recovery_plan_id: str | None = None,
    ) -> CreditLedgerEntry:
        return CreditLedgerEntry(
            id=uuid4(),
            tenant_id=wallet.tenant_id,
            kind=kind,
            delta=delta,
            balance_after=wallet.available,
            reason=reason[:255],
            idempotency_key=idempotency_key,
            recovery_plan_id=recovery_plan_id,
            subscription_id=subscription_id,
            created_at=datetime.now(tz=UTC),
        )

    def _settle_consumption(
        self,
        wallet: CreditWallet,
        reservation: CreditReservation,
        now: datetime,
    ) -> tuple[CreditWallet, CreditReservation, CreditLedgerEntry, str]:
        wallet = CreditWallet(
            id=wallet.id,
            tenant_id=wallet.tenant_id,
            allocated=wallet.allocated,
            consumed=wallet.consumed + 1,
            reserved=max(wallet.reserved - 1, 0),
            period_start=wallet.period_start,
            period_end=wallet.period_end,
            is_enforced=wallet.is_enforced,
            plan_tier=wallet.plan_tier,
            plan_name=wallet.plan_name,
            subscription_id=wallet.subscription_id,
            provider_subscription_id=wallet.provider_subscription_id,
            created_at=wallet.created_at,
            updated_at=now,
        )
        reservation = CreditReservation(
            id=reservation.id,
            tenant_id=reservation.tenant_id,
            recovery_plan_id=reservation.recovery_plan_id,
            status=CreditReservationStatus.CONSUMED,
            expires_at=reservation.expires_at,
            settled_at=now,
            created_at=reservation.created_at,
        )
        entry = self._entry(
            wallet,
            kind=CreditLedgerKind.CONSUMPTION,
            delta=0,
            reason=f"recovery plan {reservation.recovery_plan_id} completed and verified",
            idempotency_key=f"consume:{wallet.tenant_id}:{reservation.recovery_plan_id}",
            recovery_plan_id=reservation.recovery_plan_id,
        )
        return wallet, reservation, entry, "consumed"

    def _settle_release(
        self,
        wallet: CreditWallet,
        reservation: CreditReservation,
        now: datetime,
        *,
        reason: str | None = None,
    ) -> tuple[CreditWallet, CreditReservation, CreditLedgerEntry, str]:
        wallet = CreditWallet(
            id=wallet.id,
            tenant_id=wallet.tenant_id,
            allocated=wallet.allocated,
            consumed=wallet.consumed,
            reserved=max(wallet.reserved - 1, 0),
            period_start=wallet.period_start,
            period_end=wallet.period_end,
            is_enforced=wallet.is_enforced,
            plan_tier=wallet.plan_tier,
            plan_name=wallet.plan_name,
            subscription_id=wallet.subscription_id,
            provider_subscription_id=wallet.provider_subscription_id,
            created_at=wallet.created_at,
            updated_at=now,
        )
        reservation = CreditReservation(
            id=reservation.id,
            tenant_id=reservation.tenant_id,
            recovery_plan_id=reservation.recovery_plan_id,
            status=CreditReservationStatus.RELEASED,
            expires_at=reservation.expires_at,
            settled_at=now,
            created_at=reservation.created_at,
        )
        entry = self._entry(
            wallet,
            kind=CreditLedgerKind.RELEASE,
            delta=1,
            reason=(reason or f"hold released for recovery plan {reservation.recovery_plan_id}"),
            idempotency_key=f"release:{reservation.id}",
            recovery_plan_id=reservation.recovery_plan_id,
        )
        return wallet, reservation, entry, "released"

    def _expire_remaining_locked(
        self,
        wallet: CreditWallet,
        now: datetime,
        *,
        reason: str = "unused credits expired at end of paid period",
    ) -> tuple[CreditWallet, CreditLedgerEntry | None]:
        """Expire the unused remainder and reset the period counters.

        At a period boundary the wallet starts fresh: the unused remainder is
        expired into the ledger (audit keeps the full history), and the
        period-scoped counters reset to zero so "consumed" always means
        "consumed this paid period". Caller holds the row.
        """
        remaining = wallet.available
        if remaining <= 0 and wallet.consumed == 0 and wallet.allocated == 0:
            return wallet, None
        period_marker = wallet.period_end.isoformat() if wallet.period_end else now.isoformat()
        expired_wallet = CreditWallet(
            id=wallet.id,
            tenant_id=wallet.tenant_id,
            allocated=0,
            consumed=0,
            reserved=wallet.reserved,
            period_start=wallet.period_start,
            period_end=wallet.period_end,
            is_enforced=wallet.is_enforced,
            plan_tier=wallet.plan_tier,
            plan_name=wallet.plan_name,
            subscription_id=wallet.subscription_id,
            provider_subscription_id=wallet.provider_subscription_id,
            created_at=wallet.created_at,
            updated_at=now,
        )
        if remaining <= 0:
            return expired_wallet, None
        entry = CreditLedgerEntry(
            id=uuid4(),
            tenant_id=wallet.tenant_id,
            kind=CreditLedgerKind.EXPIRY,
            delta=-remaining,
            balance_after=expired_wallet.available,
            reason=reason[:255],
            idempotency_key=f"expire:{wallet.tenant_id}:{period_marker}",
            subscription_id=wallet.subscription_id,
            created_at=now,
        )
        return expired_wallet, entry

    async def _sweep_expired_reservations(
        self, tenant_id: str, *, commit: bool
    ) -> None:
        """Release holds whose TTL elapsed (lazy expiry, crash recovery)."""
        now = self._clock()
        expired = await self._repo.list_expired_active_reservations(now)
        for reservation in expired:
            if reservation.tenant_id != tenant_id:
                continue
            wallet = await self._repo.get_wallet(reservation.tenant_id)
            if wallet is None:
                continue
            released_wallet, settled, entry, _ = self._settle_release(
                wallet,
                reservation,
                now,
                reason=f"hold expired for recovery plan {reservation.recovery_plan_id}",
            )
            # Mark the reservation expired rather than released for TTL sweeps.
            settled = CreditReservation(
                id=settled.id,
                tenant_id=settled.tenant_id,
                recovery_plan_id=settled.recovery_plan_id,
                status=CreditReservationStatus.EXPIRED,
                expires_at=settled.expires_at,
                settled_at=settled.settled_at,
                created_at=settled.created_at,
            )
            if await self._repo.get_ledger_entry_by_key(entry.idempotency_key) is None:
                await self._repo.save_wallet(released_wallet)
                await self._repo.save_reservation(settled)
                await self._repo.add_ledger_entry(entry)
        if commit:
            await self._repo.commit()
