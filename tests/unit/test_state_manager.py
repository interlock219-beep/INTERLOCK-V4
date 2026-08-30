from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.domain.entities.sso_state import SSOProviderType, SSOState
from app.infrastructure.sso.state_manager import StateStore


class FakeStateStore(StateStore):
    def __init__(self) -> None:
        self._states: dict[str, SSOState] = {}

    async def create(self, state: SSOState) -> SSOState:
        self._states[state.state_token] = state
        return state

    async def get(self, state_token: str) -> SSOState | None:
        return self._states.get(state_token)

    async def mark_authorized(self, state_token: str, user_id: str) -> SSOState | None:
        state = self._states.get(state_token)
        if state is not None:
            state = SSOState(
                state_token=state.state_token,
                nonce=state.nonce,
                provider_type=state.provider_type,
                tenant_id=state.tenant_id,
                redirect_uri=state.redirect_uri,
                expires_at=state.expires_at,
                user_id=user_id,
                consumed_at=datetime.now(state.expires_at.tzinfo),
            )
            self._states[state_token] = state
        return state

    async def mark_failed(self, state_token: str) -> SSOState | None:
        state = self._states.get(state_token)
        if state is not None:
            state = SSOState(
                state_token=state.state_token,
                nonce=state.nonce,
                provider_type=state.provider_type,
                tenant_id=state.tenant_id,
                redirect_uri=state.redirect_uri,
                expires_at=state.expires_at,
                user_id=state.user_id,
                consumed_at=datetime.now(state.expires_at.tzinfo),
            )
            self._states[state_token] = state
        return state

    async def delete_expired(self, before: datetime) -> int:
        expired = [k for k, v in self._states.items() if v.expires_at < before]
        for key in expired:
            del self._states[key]
        return len(expired)


@pytest.mark.asyncio
async def test_state_store_create_and_get() -> None:
    store = FakeStateStore()
    state = SSOState(
        state_token="token-1",
        nonce="nonce-1",
        provider_type=SSOProviderType.OIDC,
        tenant_id="tenant-1",
        redirect_uri="https://example.com/callback",
        expires_at=datetime.now(UTC),
    )
    saved = await store.create(state)
    assert saved.state_token == "token-1"
    loaded = await store.get("token-1")
    assert loaded is not None
    assert loaded.nonce == "nonce-1"


@pytest.mark.asyncio
async def test_state_store_get_missing() -> None:
    store = FakeStateStore()
    assert await store.get("missing") is None


@pytest.mark.asyncio
async def test_state_store_mark_authorized() -> None:
    store = FakeStateStore()
    state = SSOState(
        state_token="token-1",
        nonce="nonce-1",
        provider_type=SSOProviderType.OIDC,
        tenant_id="tenant-1",
        redirect_uri="https://example.com/callback",
        expires_at=datetime.now(UTC),
    )
    await store.create(state)
    updated = await store.mark_authorized("token-1", "user-1")
    assert updated is not None
    assert updated.user_id == "user-1"
    assert updated.consumed_at is not None


@pytest.mark.asyncio
async def test_state_store_mark_failed() -> None:
    store = FakeStateStore()
    state = SSOState(
        state_token="token-1",
        nonce="nonce-1",
        provider_type=SSOProviderType.OIDC,
        tenant_id="tenant-1",
        redirect_uri="https://example.com/callback",
        expires_at=datetime.now(UTC),
    )
    await store.create(state)
    updated = await store.mark_failed("token-1")
    assert updated is not None
    assert updated.consumed_at is not None


@pytest.mark.asyncio
async def test_state_store_delete_expired() -> None:
    store = FakeStateStore()
    old = datetime(2020, 1, 1, tzinfo=UTC)
    future = datetime(2030, 1, 1, tzinfo=UTC)
    await store.create(
        SSOState(
            state_token="old",
            nonce="n1",
            provider_type=SSOProviderType.OIDC,
            tenant_id="t1",
            redirect_uri="https://example.com",
            expires_at=old,
        )
    )
    await store.create(
        SSOState(
            state_token="new",
            nonce="n2",
            provider_type=SSOProviderType.OIDC,
            tenant_id="t1",
            redirect_uri="https://example.com",
            expires_at=future,
        )
    )
    count = await store.delete_expired(future)
    assert count == 1
    assert await store.get("old") is None
    assert await store.get("new") is not None
