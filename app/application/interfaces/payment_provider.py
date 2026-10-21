from abc import ABC, abstractmethod
from uuid import UUID

from app.application.dto.billing import (
    CheckoutSessionResponse,
    CreateCheckoutRequest,
    PortalSessionResponse,
)
from app.domain.entities.billing_entities import Plan


class PaymentProvider(ABC):
    """Port for payment provider operations."""

    @abstractmethod
    async def create_checkout_session(
        self,
        request: CreateCheckoutRequest,
        user_id: UUID,
        tenant_id: str | None,
        plan: Plan,
    ) -> CheckoutSessionResponse:
        """Create a hosted checkout session and return the session URL.

        ``plan`` is the server-side plan record: providers must price the
        session from it (or from a pre-created Price mapped to it) and must
        never accept amounts or currencies from the client request.
        """
        ...

    @abstractmethod
    async def create_portal_session(
        self,
        user_id: UUID,
        tenant_id: str | None,
        customer_id: str | None = None,
    ) -> PortalSessionResponse:
        """Create a customer portal session for managing subscription."""
        ...

    @abstractmethod
    async def construct_webhook_event(self, payload: bytes, signature: str, secret: str) -> object:
        """Verify webhook signature and return the event object."""
        ...

    @abstractmethod
    def get_publishable_key(self) -> str | None:
        """Return the publishable key for the frontend (or None if not configured)."""
        ...
