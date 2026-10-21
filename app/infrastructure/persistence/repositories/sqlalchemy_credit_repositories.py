"""SQLAlchemy adapter for the recovery-credit repository port."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.entities.billing_entities import (
    CreditLedgerEntry,
    CreditLedgerKind,
    CreditReservation,
    CreditReservationStatus,
    CreditWallet,
)
from app.domain.exceptions.billing_errors import DuplicateCreditOperationError
from app.domain.repositories.credit_repositories import CreditRepository
from app.infrastructure.persistence.models.credit_models import (
    CreditLedgerModel,
    CreditReservationModel,
    CreditWalletModel,
)


def _wallet_to_entity(model: CreditWalletModel) -> CreditWallet:
    return CreditWallet(
        id=model.id,
        tenant_id=model.tenant_id,
        allocated=model.allocated,
        consumed=model.consumed,
        reserved=model.reserved,
        period_start=model.period_start,
        period_end=model.period_end,
        is_enforced=model.is_enforced,
        plan_tier=str(model.plan_tier),
        plan_name=model.plan_name,
        subscription_id=model.subscription_id,
        provider_subscription_id=model.provider_subscription_id,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _ledger_to_entity(model: CreditLedgerModel) -> CreditLedgerEntry:
    return CreditLedgerEntry(
        id=model.id,
        tenant_id=model.tenant_id,
        kind=CreditLedgerKind(model.kind),
        delta=model.delta,
        balance_after=model.balance_after,
        reason=model.reason,
        idempotency_key=model.idempotency_key,
        recovery_plan_id=model.recovery_plan_id,
        subscription_id=model.subscription_id,
        created_at=model.created_at,
    )


def _reservation_to_entity(model: CreditReservationModel) -> CreditReservation:
    return CreditReservation(
        id=model.id,
        tenant_id=model.tenant_id,
        recovery_plan_id=model.recovery_plan_id,
        status=CreditReservationStatus(model.status),
        expires_at=model.expires_at,
        settled_at=model.settled_at,
        created_at=model.created_at,
    )


class SQLAlchemyCreditRepository(CreditRepository):
    """Session-backed credit repository. All methods run in the caller's transaction."""

    def __init__(self, session: Session) -> None:
        self._session = session

    async def get_wallet(self, tenant_id: str) -> CreditWallet | None:
        model = self._session.scalar(
            select(CreditWalletModel).where(CreditWalletModel.tenant_id == tenant_id)
        )
        return _wallet_to_entity(model) if model else None

    async def save_wallet(self, wallet: CreditWallet) -> None:
        model = self._session.get(CreditWalletModel, wallet.id)
        if model is None:
            model = CreditWalletModel(id=wallet.id, created_at=wallet.created_at)
            self._session.add(model)
        model.tenant_id = wallet.tenant_id
        model.allocated = wallet.allocated
        model.consumed = wallet.consumed
        model.reserved = wallet.reserved
        model.period_start = wallet.period_start
        model.period_end = wallet.period_end
        model.is_enforced = wallet.is_enforced
        model.plan_tier = wallet.plan_tier
        model.plan_name = wallet.plan_name
        model.subscription_id = wallet.subscription_id
        model.provider_subscription_id = wallet.provider_subscription_id
        model.updated_at = wallet.updated_at
        self._session.flush()

    async def get_ledger_entry_by_key(self, idempotency_key: str) -> CreditLedgerEntry | None:
        model = self._session.scalar(
            select(CreditLedgerModel).where(
                CreditLedgerModel.idempotency_key == idempotency_key
            )
        )
        return _ledger_to_entity(model) if model else None

    async def add_ledger_entry(self, entry: CreditLedgerEntry) -> None:
        model = CreditLedgerModel(
            id=entry.id,
            tenant_id=entry.tenant_id,
            kind=entry.kind.value,
            delta=entry.delta,
            balance_after=entry.balance_after,
            reason=entry.reason,
            idempotency_key=entry.idempotency_key,
            recovery_plan_id=entry.recovery_plan_id,
            subscription_id=entry.subscription_id,
            created_at=entry.created_at,
        )
        self._session.add(model)
        try:
            self._session.flush()
        except IntegrityError as exc:
            self._session.rollback()
            raise DuplicateCreditOperationError(
                f"Credit ledger entry already recorded: {entry.idempotency_key}"
            ) from exc

    async def list_ledger(
        self, tenant_id: str, *, limit: int = 50, offset: int = 0
    ) -> list[CreditLedgerEntry]:
        rows = self._session.scalars(
            select(CreditLedgerModel)
            .where(CreditLedgerModel.tenant_id == tenant_id)
            .order_by(CreditLedgerModel.created_at.desc(), CreditLedgerModel.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return [_ledger_to_entity(row) for row in rows]

    async def get_active_reservation(
        self, tenant_id: str, recovery_plan_id: str
    ) -> CreditReservation | None:
        model = self._session.scalar(
            select(CreditReservationModel).where(
                CreditReservationModel.tenant_id == tenant_id,
                CreditReservationModel.recovery_plan_id == recovery_plan_id,
                CreditReservationModel.status == CreditReservationStatus.ACTIVE.value,
            )
        )
        return _reservation_to_entity(model) if model else None

    async def save_reservation(self, reservation: CreditReservation) -> None:
        model = self._session.get(CreditReservationModel, reservation.id)
        if model is None:
            model = CreditReservationModel(id=reservation.id, created_at=reservation.created_at)
            self._session.add(model)
        model.tenant_id = reservation.tenant_id
        model.recovery_plan_id = reservation.recovery_plan_id
        model.status = reservation.status.value
        model.expires_at = reservation.expires_at
        model.settled_at = reservation.settled_at
        self._session.flush()

    async def get_reservation(self, reservation_id: UUID) -> CreditReservation | None:
        model = self._session.get(CreditReservationModel, reservation_id)
        return _reservation_to_entity(model) if model else None

    async def list_expired_active_reservations(self, now: datetime) -> list[CreditReservation]:
        rows = self._session.scalars(
            select(CreditReservationModel).where(
                CreditReservationModel.status == CreditReservationStatus.ACTIVE.value,
                CreditReservationModel.expires_at < now,
            )
        )
        return [_reservation_to_entity(row) for row in rows]

    async def was_plan_consumed(self, tenant_id: str, recovery_plan_id: str) -> bool:
        model = self._session.scalar(
            select(CreditLedgerModel).where(
                CreditLedgerModel.tenant_id == tenant_id,
                CreditLedgerModel.kind == CreditLedgerKind.CONSUMPTION.value,
                CreditLedgerModel.recovery_plan_id == recovery_plan_id,
            )
        )
        return model is not None

    async def commit(self) -> None:
        self._session.commit()

    async def rollback(self) -> None:
        self._session.rollback()
