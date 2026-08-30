from datetime import UTC, datetime
from uuid import uuid4

from app.domain.entities.identity_provider import IdentityProvider, IdentityProviderType
from app.domain.entities.sso_state import SSOProviderType, SSOState
from app.domain.exceptions.domain_errors import AuthenticationError
from app.domain.repositories.identity_provider_repository import IdentityProviderRepository
from app.domain.repositories.sso_repository import SSOStateRepository
from app.domain.services.sso_services import (
    AccountLinkingService,
    SSOCallbackResult,
    SSOFlowResult,
    SSOInitiateResult,
    SSOService,
)
from app.infrastructure.sso.oidc_adapter import DefaultOIDCAdapter
from app.infrastructure.sso.saml_adapter import MockSAMLAdapter


class DefaultSSOService(SSOService):
    def __init__(
        self,
        sso_state_repository: SSOStateRepository,
        identity_provider_repository: IdentityProviderRepository,
        account_linking: AccountLinkingService,
        state_ttl_seconds: int = 600,
    ) -> None:
        self._sso_state_repository = sso_state_repository
        self._identity_provider_repository = identity_provider_repository
        self._account_linking = account_linking
        self._state_ttl_seconds = state_ttl_seconds

    async def initiate(
        self,
        provider_name: str,
        tenant_id: str | None,
        redirect_uri: str,
    ) -> SSOInitiateResult:
        provider = await self._identity_provider_repository.get_by_name(provider_name, tenant_id)
        if provider is None:
            return SSOInitiateResult(
                result=SSOFlowResult.FAILED,
                error=f"Identity provider '{provider_name}' not found.",
            )

        provider_type = SSOProviderType(provider.provider_type.value)

        from datetime import timedelta
        from secrets import token_urlsafe

        state_token = token_urlsafe(32)
        nonce = token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(seconds=self._state_ttl_seconds)
        state = SSOState(
            state_token=state_token,
            nonce=nonce,
            provider_type=provider_type,
            tenant_id=tenant_id,
            redirect_uri=redirect_uri,
            expires_at=expires_at,
        )
        await self._sso_state_repository.create(state)

        authorization_url: str | None = None
        if provider.provider_type.value == "oidc":
            oidc_adapter = DefaultOIDCAdapter()
            authorization_url = await oidc_adapter.get_authorization_url(state, provider)
        elif provider.provider_type.value == "saml":
            saml_adapter = MockSAMLAdapter()
            authorization_url = saml_adapter.generate_auth_request(state, provider)
        else:
            return SSOInitiateResult(
                result=SSOFlowResult.FAILED,
                error=f"Unsupported provider type: {provider.provider_type.value}",
            )

        return SSOInitiateResult(
            result=SSOFlowResult.PENDING,
            authorization_url=authorization_url,
            state_token=state_token,
        )

    async def handle_callback(
        self,
        state_token: str,
        *,
        code: str | None = None,
        saml_response: str | None = None,
    ) -> SSOCallbackResult:
        state = await self._sso_state_repository.get_by_state_token(state_token)
        if state is None:
            return SSOCallbackResult(
                result=SSOFlowResult.FAILED,
                error="Invalid or expired state token.",
            )

        provider = (
            await self._identity_provider_repository.get_by_name("mock-provider", state.tenant_id)
        )
        if provider is None:
            return SSOCallbackResult(
                result=SSOFlowResult.FAILED,
                error="Identity provider not found.",
            )

        try:
            if state.provider_type.value == "oidc":
                oidc_adapter = DefaultOIDCAdapter()
                provider_user_id, claims = await oidc_adapter.handle_callback(
                    state, provider, code=code
                )
            elif state.provider_type.value == "saml":
                saml_adapter = MockSAMLAdapter()
                provider_user_id = "mock-sso-user"
                claims = saml_adapter.parse_response(saml_response or "")
            else:
                return SSOCallbackResult(
                    result=SSOFlowResult.FAILED,
                    error="Unsupported provider type.",
                )
        except AuthenticationError as exc:
            await self._sso_state_repository.mark_failed(state_token)
            return SSOCallbackResult(result=SSOFlowResult.FAILED, error=str(exc))

        email = claims.get("email", f"{provider_user_id}@sso.local")
        user_id = await self._account_linking.find_user_by_sso(
            IdentityProviderType(state.provider_type.value),
            provider_user_id,
        )

        if user_id is None:
            user_id = state.user_id

        if user_id is None:
            return SSOCallbackResult(
                result=SSOFlowResult.AUTHORIZED,
                email=email,
                user_id=uuid4(),
                error="SSO account not linked. Provisioning required.",
            )

        return SSOCallbackResult(
            result=SSOFlowResult.AUTHORIZED,
            user_id=user_id,
            email=email,
        )

    async def get_providers(self, tenant_id: str | None = None) -> list[IdentityProvider]:
        return await self._identity_provider_repository.list_active(tenant_id=tenant_id)
