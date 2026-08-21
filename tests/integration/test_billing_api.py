"""Tests for billing API routes."""

import hashlib
import hmac
import json
from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register(client: TestClient, email: str, password: str) -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    assert response.status_code == 201
    return response.json()


class TestBillingRoutes:
    def test_list_plans_returns_active_plans(
        self, client: TestClient, seed_plans: None
    ) -> None:
        response = client.get("/api/v1/billing/plans")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        tiers = [p["tier"] for p in data]
        assert "free" in tiers

    def test_get_subscription_requires_auth(self, client: TestClient) -> None:
        response = client.get("/api/v1/billing/subscription")
        assert response.status_code == 401

    def test_get_usage_requires_auth(self, client: TestClient) -> None:
        response = client.get("/api/v1/billing/usage")
        assert response.status_code == 401

    def test_create_checkout_requires_auth(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/billing/checkout",
            json={"plan_id": str(uuid4()), "interval": "monthly"},
        )
        assert response.status_code == 401

    def test_webhook_requires_signature(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/billing/webhook", content=b"{}"
        )
        assert response.status_code == 400

    def test_get_publishable_key(self, client: TestClient) -> None:
        response = client.get("/api/v1/billing/publishable-key")
        assert response.status_code == 200
        data = response.json()
        assert "publishableKey" in data

    def test_get_subscription_returns_none_for_new_user(
        self, client: TestClient, seed_plans: None
    ) -> None:
        auth = _register(client, "billing@test.com", "SecurePass1!")
        response = client.get(
            "/api/v1/billing/subscription",
            headers=_auth_header(auth["access_token"]),
        )
        assert response.status_code == 200
        assert response.json() is None

    def test_get_usage_returns_empty_for_new_user(
        self, client: TestClient, seed_plans: None
    ) -> None:
        auth = _register(client, "usage@test.com", "SecurePass1!")
        response = client.get(
            "/api/v1/billing/usage",
            headers=_auth_header(auth["access_token"]),
        )
        assert response.status_code == 200
        assert response.json() == []

    def test_create_checkout_session(
        self, client: TestClient, seed_plans: None
    ) -> None:
        auth = _register(client, "checkout@test.com", "SecurePass1!")
        plans = client.get("/api/v1/billing/plans").json()
        free_plan = next(p for p in plans if p["tier"] == "free")
        response = client.post(
            "/api/v1/billing/checkout",
            headers=_auth_header(auth["access_token"]),
            json={
                "plan_id": free_plan["id"],
                "interval": "monthly",
                "success_url": "http://localhost:3000/dashboard/billing",
                "cancel_url": "http://localhost:3000/dashboard/billing",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert "session_id" in data
        assert "url" in data

    def test_webhook_idempotency(
        self, client: TestClient, seed_plans: None
    ) -> None:
        auth = _register(client, "webhook@test.com", "SecurePass1!")
        plans = client.get("/api/v1/billing/plans").json()
        free_plan = next(p for p in plans if p["tier"] == "free")

        checkout_resp = client.post(
            "/api/v1/billing/checkout",
            headers=_auth_header(auth["access_token"]),
            json={
                "plan_id": free_plan["id"],
                "interval": "monthly",
                "success_url": "http://localhost:3000/dashboard/billing",
                "cancel_url": "http://localhost:3000/dashboard/billing",
            },
        )
        assert checkout_resp.status_code == 201
        checkout_data = checkout_resp.json()
        provider_session_id = checkout_data["session_id"]

        payload = json.dumps({
            "id": "evt_test_123",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": provider_session_id,
                    "subscription": "sub_test_123",
                    "metadata": {
                        "user_id": auth["user"]["id"],
                        "plan_id": free_plan["id"],
                    },
                }
            },
        }).encode()
        secret = "whsec_test"
        signature = hmac.new(
            secret.encode(), payload, hashlib.sha256
        ).hexdigest()
        headers = {"Stripe-Signature": f"t={int(datetime.now(tz=UTC).timestamp())},v1={signature}"}

        response1 = client.post(
            "/api/v1/billing/webhook",
            content=payload,
            headers=headers,
        )
        assert response1.status_code == 200

        response2 = client.post(
            "/api/v1/billing/webhook",
            content=payload,
            headers=headers,
        )
        assert response2.status_code == 200

    def test_webhook_invalid_signature(
        self, client: TestClient, seed_plans: None
    ) -> None:
        payload = b"{}"
        headers = {"Stripe-Signature": "invalid"}
        response = client.post(
            "/api/v1/billing/webhook",
            content=payload,
            headers=headers,
        )
        assert response.status_code == 400

    def test_cancel_subscription_requires_auth(
        self, client: TestClient
    ) -> None:
        response = client.post("/api/v1/billing/cancel")
        assert response.status_code == 401

    def test_create_portal_requires_auth(self, client: TestClient) -> None:
        response = client.post("/api/v1/billing/portal")
        assert response.status_code == 401

    def test_record_usage_requires_auth(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/billing/usage",
            json={"resource_type": "intents_per_day", "quantity": 1},
        )
        assert response.status_code == 401

    def test_create_portal_session(
        self, client: TestClient, seed_plans: None
    ) -> None:
        auth = _register(client, "portal@test.com", "SecurePass1!")
        response = client.post(
            "/api/v1/billing/portal",
            headers=_auth_header(auth["access_token"]),
        )
        assert response.status_code == 200
        data = response.json()
        assert "url" in data
        assert "expires_at" in data

    def test_record_usage_returns_result(
        self, client: TestClient, seed_plans: None
    ) -> None:
        auth = _register(client, "record@test.com", "SecurePass1!")
        plans = client.get("/api/v1/billing/plans").json()
        free_plan = next(p for p in plans if p["tier"] == "free")
        checkout_resp = client.post(
            "/api/v1/billing/checkout",
            headers=_auth_header(auth["access_token"]),
            json={
                "plan_id": free_plan["id"],
                "interval": "monthly",
                "success_url": "http://localhost:3000/dashboard/billing",
                "cancel_url": "http://localhost:3000/dashboard/billing",
            },
        )
        assert checkout_resp.status_code == 201
        provider_session_id = checkout_resp.json()["session_id"]

        payload = json.dumps({
            "id": provider_session_id,
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": provider_session_id,
                    "subscription": "sub_test_portal",
                    "metadata": {
                        "user_id": auth["user"]["id"],
                        "plan_id": free_plan["id"],
                    },
                }
            },
        }).encode()
        secret = "whsec_test"
        signature = hmac.new(
            secret.encode(), payload, hashlib.sha256
        ).hexdigest()
        headers = {"Stripe-Signature": f"t={int(datetime.now(tz=UTC).timestamp())},v1={signature}"}
        client.post(
            "/api/v1/billing/webhook",
            content=payload,
            headers=headers,
        )

        response = client.post(
            "/api/v1/billing/usage",
            headers=_auth_header(auth["access_token"]),
            json={"resource_type": "intents_per_day", "quantity": 1},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["allowed"] is True
        assert data["reason"] == "recorded"

    def test_get_billing_overview(
        self, client: TestClient, seed_plans: None
    ) -> None:
        auth = _register(client, "overview@test.com", "SecurePass1!")
        plans = client.get("/api/v1/billing/plans").json()
        free_plan = next(p for p in plans if p["tier"] == "free")
        checkout_resp = client.post(
            "/api/v1/billing/checkout",
            headers=_auth_header(auth["access_token"]),
            json={
                "plan_id": free_plan["id"],
                "interval": "monthly",
                "success_url": "http://localhost:3000/dashboard/billing",
                "cancel_url": "http://localhost:3000/dashboard/billing",
            },
        )
        assert checkout_resp.status_code == 201
        provider_session_id = checkout_resp.json()["session_id"]

        payload = json.dumps({
            "id": provider_session_id,
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": provider_session_id,
                    "subscription": "sub_test_overview",
                    "metadata": {
                        "user_id": auth["user"]["id"],
                        "plan_id": free_plan["id"],
                    },
                }
            },
        }).encode()
        secret = "whsec_test"
        signature = hmac.new(
            secret.encode(), payload, hashlib.sha256
        ).hexdigest()
        headers = {"Stripe-Signature": f"t={int(datetime.now(tz=UTC).timestamp())},v1={signature}"}
        webhook_resp = client.post(
            "/api/v1/billing/webhook",
            content=payload,
            headers=headers,
        )
        assert webhook_resp.status_code == 200

        sub_resp = client.get(
            "/api/v1/billing/subscription",
            headers=_auth_header(auth["access_token"]),
        )
        assert sub_resp.status_code == 200
        assert sub_resp.json() is not None

        response = client.get(
            "/api/v1/billing/overview",
            headers=_auth_header(auth["access_token"]),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["subscription"] is not None
        assert data["plan"] is not None
        assert isinstance(data["usage"], list)

    def test_create_checkout_invalid_plan(
        self, client: TestClient, seed_plans: None
    ) -> None:
        auth = _register(client, "invalidplan@test.com", "SecurePass1!")
        response = client.post(
            "/api/v1/billing/checkout",
            headers=_auth_header(auth["access_token"]),
            json={
                "plan_id": str(uuid4()),
                "interval": "monthly",
                "success_url": "http://localhost:3000/dashboard/billing",
                "cancel_url": "http://localhost:3000/dashboard/billing",
            },
        )
        assert response.status_code == 404

    def test_create_checkout_already_subscribed(
        self, client: TestClient, seed_plans: None
    ) -> None:
        auth = _register(client, "subscribed2@test.com", "SecurePass1!")
        plans = client.get("/api/v1/billing/plans").json()
        free_plan = next(p for p in plans if p["tier"] == "free")
        response = client.post(
            "/api/v1/billing/checkout",
            headers=_auth_header(auth["access_token"]),
            json={
                "plan_id": free_plan["id"],
                "interval": "monthly",
                "success_url": "http://localhost:3000/dashboard/billing",
                "cancel_url": "http://localhost:3000/dashboard/billing",
            },
        )
        assert response.status_code == 201
        provider_session_id = response.json()["session_id"]

        payload = json.dumps({
            "id": provider_session_id,
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": provider_session_id,
                    "subscription": "sub_test_dup",
                    "metadata": {
                        "user_id": auth["user"]["id"],
                        "plan_id": free_plan["id"],
                    },
                }
            },
        }).encode()
        secret = "whsec_test"
        signature = hmac.new(
            secret.encode(), payload, hashlib.sha256
        ).hexdigest()
        headers = {"Stripe-Signature": f"t={int(datetime.now(tz=UTC).timestamp())},v1={signature}"}
        client.post(
            "/api/v1/billing/webhook",
            content=payload,
            headers=headers,
        )

        response2 = client.post(
            "/api/v1/billing/checkout",
            headers=_auth_header(auth["access_token"]),
            json={
                "plan_id": free_plan["id"],
                "interval": "monthly",
                "success_url": "http://localhost:3000/dashboard/billing",
                "cancel_url": "http://localhost:3000/dashboard/billing",
            },
        )
        assert response2.status_code == 409

    def test_cancel_subscription_no_active(
        self, client: TestClient, seed_plans: None
    ) -> None:
        auth = _register(client, "nosub@test.com", "SecurePass1!")
        response = client.post(
            "/api/v1/billing/cancel",
            headers=_auth_header(auth["access_token"]),
        )
        assert response.status_code == 404

    def test_create_portal_session_no_checkout(
        self, client: TestClient, seed_plans: None
    ) -> None:
        auth = _register(client, "noportalsub@test.com", "SecurePass1!")
        response = client.post(
            "/api/v1/billing/portal",
            headers=_auth_header(auth["access_token"]),
        )
        assert response.status_code == 200
        data = response.json()
        assert "url" in data
