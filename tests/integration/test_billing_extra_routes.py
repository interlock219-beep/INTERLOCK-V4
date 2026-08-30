"""Tests for billing API routes - covering uncovered branches."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.domain.exceptions.billing_errors import (
    SubscriptionAlreadyExistsError,
)


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register(client: TestClient, email: str, password: str) -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    assert response.status_code == 201
    return response.json()


class TestBillingUncoveredBranches:
    def test_get_payment_provider_stripe(self, client: TestClient, seed_plans) -> None:
        """Test that Stripe provider is used when credentials are set."""
        with patch("app.presentation.api.v1.routes.billing.get_settings") as mock_settings, \
             patch("app.presentation.api.v1.routes.billing.StripePaymentProvider") as mock_stripe:
            mock_settings.return_value.stripe_secret_key = "sk_test_123"
            mock_settings.return_value.stripe_webhook_secret = "whsec_test"
            mock_settings.return_value.stripe_publishable_key = "pk_test_123"
            mock_settings.return_value.app_env = "production"
            mock_stripe.return_value.get_publishable_key.return_value = "pk_test_123"
            response = client.get("/api/v1/billing/publishable-key")
            assert response.status_code == 200

    def test_get_payment_provider_non_dev_no_credentials(self, client: TestClient) -> None:
        """Test that ValueError is raised in non-dev without credentials."""
        from app.infrastructure.config.settings import Settings
        from app.presentation.api.v1.routes.billing import _get_payment_provider

        settings = Settings(
            stripe_secret_key="",
            stripe_webhook_secret="",
            stripe_publishable_key="",
            app_env="production",
            redis_url="redis://localhost:6379/0",
            database_url="postgresql://localhost/intentlock",
        )
        with pytest.raises(ValueError, match="Stripe credentials"):
            _get_payment_provider(settings)

    def test_create_checkout_plan_not_found(self, client: TestClient, seed_plans) -> None:
        auth = _register(client, "checkoutplan@test.com", "SecurePass1!")
        response = client.post(
            "/api/v1/billing/checkout",
            headers=_auth_header(auth["access_token"]),
            json={
                "plan_id": "00000000-0000-0000-0000-000000000000",
                "interval": "monthly",
                "success_url": "http://localhost:3000/success",
                "cancel_url": "http://localhost:3000/cancel",
            },
        )
        assert response.status_code == 404

    def test_create_checkout_already_exists(self, client: TestClient, seed_plans) -> None:
        auth = _register(client, "checkoutexists@test.com", "SecurePass1!")
        plans = client.get("/api/v1/billing/plans").json()
        free_plan = next(p for p in plans if p["tier"] == "free")
        with patch(
            "app.application.use_cases.create_checkout_session.CreateCheckoutSessionUseCase.execute",
            side_effect=SubscriptionAlreadyExistsError("Already subscribed"),
        ):
            response = client.post(
                "/api/v1/billing/checkout",
                headers=_auth_header(auth["access_token"]),
                json={
                    "plan_id": free_plan["id"],
                    "interval": "monthly",
                    "success_url": "http://localhost:3000/success",
                    "cancel_url": "http://localhost:3000/cancel",
                },
            )
            assert response.status_code == 409

    def test_create_checkout_generic_error(self, client: TestClient, seed_plans) -> None:
        auth = _register(client, "checkouterror@test.com", "SecurePass1!")
        plans = client.get("/api/v1/billing/plans").json()
        free_plan = next(p for p in plans if p["tier"] == "free")
        with patch(
            "app.application.use_cases.create_checkout_session.CreateCheckoutSessionUseCase.execute",
            side_effect=Exception("Provider error"),
        ):
            response = client.post(
                "/api/v1/billing/checkout",
                headers=_auth_header(auth["access_token"]),
                json={
                    "plan_id": free_plan["id"],
                    "interval": "monthly",
                    "success_url": "http://localhost:3000/success",
                    "cancel_url": "http://localhost:3000/cancel",
                },
            )
            assert response.status_code == 502

    def test_webhook_missing_signature(self, client: TestClient) -> None:
        response = client.post("/api/v1/billing/webhook", content=b"{}")
        assert response.status_code == 400
        assert "Missing signature" in response.json()["detail"]

    def test_webhook_value_error(self, client: TestClient) -> None:
        with patch(
            "app.application.use_cases.handle_webhook.HandleWebhookUseCase.execute",
            side_effect=ValueError("Invalid payload"),
        ):
            response = client.post(
                "/api/v1/billing/webhook",
                content=b"{}",
                headers={"Stripe-Signature": "test"},
            )
            assert response.status_code == 400

    def test_webhook_generic_error(self, client: TestClient) -> None:
        with patch(
            "app.application.use_cases.handle_webhook.HandleWebhookUseCase.execute",
            side_effect=Exception("Processing error"),
        ):
            response = client.post(
                "/api/v1/billing/webhook",
                content=b"{}",
                headers={"Stripe-Signature": "test"},
            )
            assert response.status_code == 400

    def test_create_portal_session_value_error(self, client: TestClient, seed_plans) -> None:
        auth = _register(client, "portalerror@test.com", "SecurePass1!")
        with patch(
            "app.presentation.api.v1.routes.billing.MockPaymentProvider.create_portal_session",
            side_effect=ValueError("No customer"),
        ):
            response = client.post(
                "/api/v1/billing/portal",
                headers=_auth_header(auth["access_token"]),
            )
            assert response.status_code == 400

    def test_get_billing_overview_no_plan(self, client: TestClient, seed_plans) -> None:
        """Test overview when user has no subscription/plan."""
        auth = _register(client, "overviewnoplan@test.com", "SecurePass1!")
        response = client.get(
            "/api/v1/billing/overview",
            headers=_auth_header(auth["access_token"]),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["plan"] is None
        assert data["subscription"] is None
        assert data["usage"] == []
