"""Repository port for the recovery-credit persistence set.

Kept separate from ``billing_repositories`` because credits are tenant-scoped
(organization wallet + append-only ledger) while the legacy billing rows are
user-scoped.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from app.domain.entities.billing_entities import (
    CreditLedgerEntry,
    CreditReservation,
    CreditWallet,
)


class CreditRepository(ABC):
    """Async persistence port for wallets, ledger and reservations."""

    @abstractmethod
    async def get_wallet(self, tenant_id: str) -> CreditWallet | None:
        """Return the tenant wallet, or None when the tenant has never been billed."""

    @abstractmethod
    async def save_wallet(self, wallet: CreditWallet) -> None:
        """Insert or update the wallet row inside the caller's transaction."""

    @abstractmethod
    async def get_ledger_entry_by_key(self, idempotency_key: str) -> CreditLedgerEntry | None:
        """Look up a ledger entry by its unique idempotency key."""

    @abstractmethod
    async def add_ledger_entry(self, entry: CreditLedgerEntry) -> None:
        """Append a ledger entry. Must raise on unique-key violation."""

    @abstractmethod
    async def list_ledger(
        self, tenant_id: str, *, limit: int = 50, offset: int = 0
    ) -> list[CreditLedgerEntry]:
        """Newest-first page of the tenant's ledger."""

    @abstractmethod
    async def get_active_reservation(
        self, tenant_id: str, recovery_plan_id: str
    ) -> CreditReservation | None:
        """Return the active hold for this recovery plan, if one exists."""

    @abstractmethod
    async def save_reservation(self, reservation: CreditReservation) -> None:
        """Insert or update a reservation inside the caller's transaction."""

    @abstractmethod
    async def get_reservation(self, reservation_id: UUID) -> CreditReservation | None:
        """Load one reservation by id (used when settling holds)."""

    @abstractmethod
    async def list_expired_active_reservations(self, now: datetime) -> list[CreditReservation]:
        """Active holds whose TTL has elapsed (for lazy expiry sweeps)."""

    @abstractmethod
    async def was_plan_consumed(self, tenant_id: str, recovery_plan_id: str) -> bool:
        """True when a consumption entry already exists for this plan."""

    @abstractmethod
    async def commit(self) -> None:
        """Commit the caller's transaction (flushes + commits)."""

    @abstractmethod
    async def rollback(self) -> None:
        """Roll the caller's transaction back."""
