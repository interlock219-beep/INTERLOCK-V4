"""Billing webhooks -> recovery-credit allocation (idempotent, verified-only).

Covers the mission's webhook matrix: verified payment allocates, duplicate
events allocate once, renewals allocate exactly once per period, failed
payments allocate nothing, upgrades grant the difference, cancellation
expires the remainder and disables enforcement.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.infrastructure.persistence.models import (
    PlanModel,
    SubscriptionModel,
)
from app.infrastructure.persistence.models.credit_models import (
    CreditLedgerModel,
    CreditWalletModel,
)

WEBHOOK_SECRET = "whsec_test"


def _sign(payload: bytes) -> dict[str, str]:
    digest = hmac.new(WEBHOOK_SECRET.encode(), payload, hashlib.sha256).hexdigest()
    return {"Stripe-Signature": f"t={int(datetime.now(tz=UTC).timestamp())},v1={digest}"}


def _post_event(client: TestClient, event: dict) -> None:
    payload = json.dumps(event).encode()
    response = client.post(
        "/api/v1/billing/webhook", content=payload, headers=_sign(payload)
    )
    assert response.status_code == 200, response.text


def _plan_id(db_session: Session, tier: str) -> UUID:
    plan = db_session.query(PlanModel).filter(PlanModel.tier == tier).one()
    return plan.id


def _seed_subscription(
    db_session: Session,
    *,
    provider_sub_id: str,
    tenant_id: str,
    plan_tier: str,
    user_id: UUID | None = None,
) -> UUID:
    now = datetime.now(tz=UTC)
    subscription_id = uuid4()
    db_session.add(
        SubscriptionModel(
            id=subscription_id,
            user_id=user_id or uuid4(),
            tenant_id=tenant_id,
            plan_id=_plan_id(db_session, plan_tier),
            status="active",
            interval="monthly",
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
            provider_subscription_id=provider_sub_id,
            created_at=now,
            updated_at=now,
        )
    )
    db_session.commit()
    return subscription_id


def _invoice_paid_event(
    provider_sub_id: str,
    *,
    event_id: str,
    start: datetime,
    end: datetime,
    amount: int = 3000,
) -> dict:
    return {
        "id": event_id,
        "type": "invoice.paid",
        "data": {
            "object": {
                "id": event_id,
                "subscription": provider_sub_id,
                "amount_paid": amount,
                "currency": "usd",
                "lines": {
                    "data": [
                        {
                            "period": {
                                "start": int(start.timestamp()),
                                "end": int(end.timestamp()),
                            }
                        }
                    ]
                },
            }
        },
    }


def _wallet(db_session: Session, tenant_id: str) -> CreditWalletModel | None:
    return (
        db_session.query(CreditWalletModel)
        .filter(CreditWalletModel.tenant_id == tenant_id)
        .one_or_none()
    )


def _available(wallet: CreditWalletModel) -> int:
    """Domain invariant: available = allocated - consumed - reserved."""
    return wallet.allocated - wallet.consumed - wallet.reserved


def _kinds(db_session: Session, tenant_id: str) -> list[str]:
    rows = (
        db_session.query(CreditLedgerModel)
        .filter(CreditLedgerModel.tenant_id == tenant_id)
        .order_by(CreditLedgerModel.created_at)
        .all()
    )
    return [row.kind for row in rows]


class TestInvoicePaidAllocation:
    def test_pro_payment_allocates_250_credits(
        self, client: TestClient, seed_plans: None, db_session: Session
    ) -> None:
        tenant = f"tenant-wh-pro-{uuid4().hex[:6]}"
        _seed_subscription(
            db_session, provider_sub_id="sub_pro_1", tenant_id=tenant, plan_tier="pro"
        )
        now = datetime.now(tz=UTC)
        _post_event(
            client,
            _invoice_paid_event(
                "sub_pro_1",
                event_id="evt_in_pro_1",
                start=now,
                end=now + timedelta(days=30),
            ),
        )
        wallet = _wallet(db_session, tenant)
        assert wallet is not None
        assert wallet.allocated == 250
        assert _available(wallet) == 250
        assert wallet.is_enforced is True
        assert "allocation" in _kinds(db_session, tenant)

    def test_starter_payment_allocates_100_credits(
        self, client: TestClient, seed_plans: None, db_session: Session
    ) -> None:
        tenant = f"tenant-wh-st-{uuid4().hex[:6]}"
        _seed_subscription(
            db_session, provider_sub_id="sub_st_1", tenant_id=tenant, plan_tier="starter"
        )
        now = datetime.now(tz=UTC)
        _post_event(
            client,
            _invoice_paid_event(
                "sub_st_1",
                event_id="evt_in_st_1",
                start=now,
                end=now + timedelta(days=30),
                amount=1500,
            ),
        )
        wallet = _wallet(db_session, tenant)
        assert wallet is not None and wallet.allocated == 100

    def test_duplicate_webhook_event_id_allocates_once(
        self, client: TestClient, seed_plans: None, db_session: Session
    ) -> None:
        tenant = f"tenant-wh-dup-{uuid4().hex[:6]}"
        _seed_subscription(
            db_session, provider_sub_id="sub_dup_1", tenant_id=tenant, plan_tier="pro"
        )
        now = datetime.now(tz=UTC)
        event = _invoice_paid_event(
            "sub_dup_1", event_id="evt_dup_1", start=now, end=now + timedelta(days=30)
        )
        _post_event(client, event)
        _post_event(client, event)  # exact replay: webhook dedupe kicks in
        wallet = _wallet(db_session, tenant)
        assert wallet is not None and wallet.allocated == 250
        assert _kinds(db_session, tenant).count("allocation") == 1

    def test_same_period_new_event_id_allocates_once(
        self, client: TestClient, seed_plans: None, db_session: Session
    ) -> None:
        tenant = f"tenant-wh-same-{uuid4().hex[:6]}"
        _seed_subscription(
            db_session, provider_sub_id="sub_same_1", tenant_id=tenant, plan_tier="pro"
        )
        now = datetime.now(tz=UTC)
        _post_event(
            client,
            _invoice_paid_event(
                "sub_same_1", event_id="evt_same_1", start=now, end=now + timedelta(days=30)
            ),
        )
        # A different provider event for the SAME billing period (Stripe
        # redeliveries / expanded replays): the ledger key blocks a regrant.
        _post_event(
            client,
            _invoice_paid_event(
                "sub_same_1", event_id="evt_same_2", start=now, end=now + timedelta(days=30)
            ),
        )
        wallet = _wallet(db_session, tenant)
        assert wallet is not None and wallet.allocated == 250

    def test_renewal_allocates_the_next_period_exactly_once(
        self, client: TestClient, seed_plans: None, db_session: Session
    ) -> None:
        tenant = f"tenant-wh-ren-{uuid4().hex[:6]}"
        _seed_subscription(
            db_session, provider_sub_id="sub_ren_1", tenant_id=tenant, plan_tier="pro"
        )
        now = datetime.now(tz=UTC)
        _post_event(
            client,
            _invoice_paid_event(
                "sub_ren_1", event_id="evt_ren_1", start=now, end=now + timedelta(days=30)
            ),
        )
        next_start = now + timedelta(days=30)
        _post_event(
            client,
            _invoice_paid_event(
                "sub_ren_1",
                event_id="evt_ren_2",
                start=next_start,
                end=next_start + timedelta(days=30),
            ),
        )
        # Replay of the renewal must not allocate a third time.
        _post_event(
            client,
            _invoice_paid_event(
                "sub_ren_1",
                event_id="evt_ren_3",
                start=next_start,
                end=next_start + timedelta(days=30),
            ),
        )
        db_session.expire_all()
        wallet = _wallet(db_session, tenant)
        assert wallet is not None
        assert wallet.allocated == 250  # new period's allowance, not 750
        kinds = _kinds(db_session, tenant)
        assert kinds.count("allocation") == 2
        assert "expiry" in kinds  # unused remainder of period 1 expired


class TestFailedPayment:
    def test_failed_payment_allocates_nothing_and_marks_past_due(
        self, client: TestClient, seed_plans: None, db_session: Session
    ) -> None:
        tenant = f"tenant-wh-fail-{uuid4().hex[:6]}"
        subscription_id = _seed_subscription(
            db_session, provider_sub_id="sub_fail_1", tenant_id=tenant, plan_tier="pro"
        )
        _post_event(
            client,
            {
                "id": "evt_fail_1",
                "type": "invoice.payment_failed",
                "data": {
                    "object": {
                        "id": "in_fail_1",
                        "subscription": "sub_fail_1",
                        "amount_due": 3000,
                        "currency": "usd",
                    }
                },
            },
        )
        db_session.expire_all()
        assert _wallet(db_session, tenant) is None  # no credits granted
        subscription = db_session.get(SubscriptionModel, subscription_id)
        assert subscription is not None
        assert subscription.status.value == "past_due"

    def test_failed_payment_keeps_existing_period_credits(
        self, client: TestClient, seed_plans: None, db_session: Session
    ) -> None:
        tenant = f"tenant-wh-keep-{uuid4().hex[:6]}"
        _seed_subscription(
            db_session, provider_sub_id="sub_keep_1", tenant_id=tenant, plan_tier="pro"
        )
        now = datetime.now(tz=UTC)
        _post_event(
            client,
            _invoice_paid_event(
                "sub_keep_1", event_id="evt_keep_1", start=now, end=now + timedelta(days=30)
            ),
        )
        _post_event(
            client,
            {
                "id": "evt_keep_fail",
                "type": "invoice.payment_failed",
                "data": {
                    "object": {
                        "id": "in_keep_fail",
                        "subscription": "sub_keep_1",
                        "amount_due": 3000,
                        "currency": "usd",
                    }
                },
            },
        )
        db_session.expire_all()
        wallet = _wallet(db_session, tenant)
        assert wallet is not None and _available(wallet) == 250  # already paid for


class TestPlanChangesAndCancellation:
    def test_upgrade_event_grants_the_difference(
        self, client: TestClient, seed_plans: None, db_session: Session
    ) -> None:
        tenant = f"tenant-wh-up-{uuid4().hex[:6]}"
        _seed_subscription(
            db_session,
            provider_sub_id="sub_up_1",
            tenant_id=tenant,
            plan_tier="starter",
        )
        now = datetime.now(tz=UTC)
        _post_event(
            client,
            _invoice_paid_event(
                "sub_up_1",
                event_id="evt_up_1",
                start=now,
                end=now + timedelta(days=30),
                amount=1500,
            ),
        )
        _post_event(
            client,
            {
                "id": "evt_up_2",
                "type": "customer.subscription.updated",
                "data": {
                    "object": {
                        "id": "sub_up_1",
                        "status": "active",
                        "current_period_start": int(now.timestamp()),
                        "current_period_end": int((now + timedelta(days=30)).timestamp()),
                        "metadata": {"plan_tier": "pro"},
                    }
                },
            },
        )
        db_session.expire_all()
        wallet = _wallet(db_session, tenant)
        assert wallet is not None
        assert wallet.allocated == 250  # 100 starter + 150 upgrade difference
        assert "adjustment" in _kinds(db_session, tenant)

    def test_downgrade_defers_to_renewal(
        self, client: TestClient, seed_plans: None, db_session: Session
    ) -> None:
        tenant = f"tenant-wh-down-{uuid4().hex[:6]}"
        _seed_subscription(
            db_session, provider_sub_id="sub_down_1", tenant_id=tenant, plan_tier="pro"
        )
        now = datetime.now(tz=UTC)
        _post_event(
            client,
            _invoice_paid_event(
                "sub_down_1", event_id="evt_down_1", start=now, end=now + timedelta(days=30)
            ),
        )
        _post_event(
            client,
            {
                "id": "evt_down_2",
                "type": "customer.subscription.updated",
                "data": {
                    "object": {
                        "id": "sub_down_1",
                        "status": "active",
                        "current_period_start": int(now.timestamp()),
                        "current_period_end": int((now + timedelta(days=30)).timestamp()),
                        "metadata": {"plan_tier": "starter"},
                    }
                },
            },
        )
        db_session.expire_all()
        wallet = _wallet(db_session, tenant)
        assert wallet is not None and wallet.allocated == 250  # nothing clawed back

    def test_cancellation_expires_remainder_and_disables_enforcement(
        self, client: TestClient, seed_plans: None, db_session: Session
    ) -> None:
        tenant = f"tenant-wh-can-{uuid4().hex[:6]}"
        _seed_subscription(
            db_session, provider_sub_id="sub_can_1", tenant_id=tenant, plan_tier="pro"
        )
        now = datetime.now(tz=UTC)
        _post_event(
            client,
            _invoice_paid_event(
                "sub_can_1", event_id="evt_can_1", start=now, end=now + timedelta(days=30)
            ),
        )
        _post_event(
            client,
            {
                "id": "evt_can_2",
                "type": "customer.subscription.deleted",
                "data": {"object": {"id": "sub_can_1"}},
            },
        )
        db_session.expire_all()
        wallet = _wallet(db_session, tenant)
        assert wallet is not None
        assert wallet.is_enforced is False
        assert _available(wallet) == 0
        assert "expiry" in _kinds(db_session, tenant)


class TestInvoiceRecording:
    def test_paid_invoice_is_recorded_once(
        self,
        client: TestClient,
        seed_plans: None,
        db_session: Session,
    ) -> None:
        from app.infrastructure.persistence.models import InvoiceModel

        tenant = f"tenant-wh-rec-{uuid4().hex[:6]}"
        _seed_subscription(
            db_session, provider_sub_id="sub_rec_1", tenant_id=tenant, plan_tier="pro"
        )
        now = datetime.now(tz=UTC)
        event = _invoice_paid_event(
            "sub_rec_1", event_id="in_rec_1", start=now, end=now + timedelta(days=30)
        )
        _post_event(client, event)
        _post_event(client, event)  # duplicate delivery
        db_session.expire_all()
        invoices = (
            db_session.query(InvoiceModel)
            .filter(InvoiceModel.provider_invoice_id == "in_rec_1")
            .all()
        )
        assert len(invoices) == 1
        assert invoices[0].status == "paid"
        assert invoices[0].amount_cents == 3000
        assert invoices[0].paid_at is not None
