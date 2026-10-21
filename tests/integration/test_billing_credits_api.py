"""Credits API: wallet summary, ledger history and tenant isolation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domain.services.recovery_credit_service import RecoveryCreditService
from app.infrastructure.persistence.repositories.sqlalchemy_credit_repositories import (
    SQLAlchemyCreditRepository,
)


def _register(client: TestClient, email: str, tenant_id: str) -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "SecurePass1!", "tenant_id": tenant_id},
    )
    assert response.status_code == 201
    return response.json()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _allocate(db_session: Session, tenant: str, amount: int, key: str) -> None:
    service = RecoveryCreditService(SQLAlchemyCreditRepository(db_session))
    now = datetime.now(tz=UTC)
    await service.allocate(
        tenant,
        amount=amount,
        period_start=now,
        period_end=now + timedelta(days=30),
        idempotency_key=key,
        reason="paid period allowance",
        plan_tier="pro",
        plan_name="Pro",
    )


class TestCreditSummaryEndpoint:
    def test_credits_requires_auth(self, client: TestClient) -> None:
        response = client.get("/api/v1/billing/credits")
        assert response.status_code == 401

    def test_evaluation_tenant_sees_zero_unenforced(
        self, client: TestClient, seed_plans: None
    ) -> None:
        auth = _register(client, f"credits-eval-{uuid4().hex[:8]}@test.com", "tenant-eval")
        response = client.get(
            "/api/v1/billing/credits", headers=_auth(auth["access_token"])
        )
        assert response.status_code == 200
        body = response.json()
        assert body["billing_enforced"] is False
        assert body["available"] == 0
        assert body["allocated"] == 0

    def test_wallet_summary_reflects_allocation(
        self, client: TestClient, seed_plans: None, db_session: Session
    ) -> None:
        import asyncio

        tenant = f"tenant-summary-{uuid4().hex[:8]}"
        asyncio.run(_allocate(db_session, tenant, 250, f"alloc:{tenant}:1"))
        auth = _register(client, f"credits-sum-{uuid4().hex[:8]}@test.com", tenant)
        response = client.get(
            "/api/v1/billing/credits", headers=_auth(auth["access_token"])
        )
        assert response.status_code == 200
        body = response.json()
        assert body["billing_enforced"] is True
        assert body["available"] == 250
        assert body["allocated"] == 250
        assert body["plan_tier"] == "pro"
        assert body["allowance"] == 250  # from the central plan registry
        assert body["period_end"] is not None


class TestCreditLedgerEndpoint:
    def test_ledger_requires_auth(self, client: TestClient) -> None:
        assert client.get("/api/v1/billing/credits/ledger").status_code == 401

    def test_ledger_lists_entries_newest_first(
        self, client: TestClient, seed_plans: None, db_session: Session
    ) -> None:
        import asyncio

        tenant = f"tenant-ledger-{uuid4().hex[:8]}"
        asyncio.run(_allocate(db_session, tenant, 250, f"alloc:{tenant}:1"))
        service = RecoveryCreditService(SQLAlchemyCreditRepository(db_session))
        hold = asyncio.run(service.reserve_for_execution(tenant, "plan-ledger-1"))
        assert hold is not None
        asyncio.run(service.finalize_hold(hold, billable=True))

        auth = _register(client, f"credits-led-{uuid4().hex[:8]}@test.com", tenant)
        response = client.get(
            "/api/v1/billing/credits/ledger", headers=_auth(auth["access_token"])
        )
        assert response.status_code == 200
        entries = response.json()
        assert [e["kind"] for e in entries] == [
            "consumption",
            "reservation",
            "allocation",
        ]
        assert entries[0]["recovery_plan_id"] == "plan-ledger-1"
        assert entries[0]["balance_after"] == 249  # after the one charge
        assert entries[-1]["balance_after"] == 250  # just after allocation

    def test_ledger_is_isolated_between_tenants(
        self, client: TestClient, seed_plans: None, db_session: Session
    ) -> None:
        import asyncio

        tenant_a = f"tenant-iso-a-{uuid4().hex[:8]}"
        asyncio.run(_allocate(db_session, tenant_a, 100, f"alloc:{tenant_a}:1"))
        auth_b = _register(client, f"credits-iso-{uuid4().hex[:8]}@test.com", "tenant-iso-b")
        response = client.get(
            "/api/v1/billing/credits/ledger", headers=_auth(auth_b["access_token"])
        )
        assert response.status_code == 200
        assert response.json() == []  # tenant B sees nothing of tenant A

    def test_ledger_pagination_bounds(
        self, client: TestClient, seed_plans: None, db_session: Session
    ) -> None:
        import asyncio

        tenant = f"tenant-page-{uuid4().hex[:8]}"
        asyncio.run(_allocate(db_session, tenant, 100, f"alloc:{tenant}:1"))
        auth = _register(client, f"credits-page-{uuid4().hex[:8]}@test.com", tenant)
        response = client.get(
            "/api/v1/billing/credits/ledger?page=1&page_size=1",
            headers=_auth(auth["access_token"]),
        )
        assert response.status_code == 200
        assert len(response.json()) == 1


class TestInvoiceHistoryEndpoint:
    def test_invoices_require_auth(self, client: TestClient) -> None:
        assert client.get("/api/v1/billing/invoices").status_code == 401

    def test_invoices_empty_without_subscription(
        self, client: TestClient, seed_plans: None
    ) -> None:
        auth = _register(client, f"credits-inv-{uuid4().hex[:8]}@test.com", "tenant-inv")
        response = client.get(
            "/api/v1/billing/invoices", headers=_auth(auth["access_token"])
        )
        assert response.status_code == 200
        assert response.json() == []
