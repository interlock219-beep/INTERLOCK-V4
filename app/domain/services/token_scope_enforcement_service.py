from __future__ import annotations
import hashlib
import logging
from typing import Any

from app.domain.value_objects.authorization_decision import AuthorizationDecision


logger = logging.getLogger(__name__)


class TokenScopeEnforcementService:
    """Enforces scope restrictions on execution tokens.

    This service provides centralized enforcement of token scope restrictions
    including action, resource, session, tenant, and parameter binding checks.
    It is used by the execution token service and other authorization layers.
    """

    @staticmethod
    def compute_resource_hash(resource: str) -> str:
        """Compute a tamper-evident SHA-256 hash of a resource path.

        Args:
            resource: The resource path to hash.

        Returns:
            Hex-encoded SHA-256 digest of the UTF-8 encoded resource string.
        """
        return hashlib.sha256(resource.encode("utf-8")).hexdigest()

    @staticmethod
    def compute_param_hash(params: dict[str, Any]) -> str:
        """Compute a canonical SHA-256 hash of a parameter set.

        Keys are sorted lexicographically to ensure deterministic output
        regardless of the original insertion order of the dictionary.

        Args:
            params: Dictionary of parameters to hash.

        Returns:
            Hex-encoded SHA-256 digest of the canonical (sorted) parameter
            key set.
        """
        canonical = sorted(str(k) for k in params)
        return hashlib.sha256(str(canonical).encode("utf-8")).hexdigest()

    def enforce_scope(
        self,
        token_payload: dict[str, Any],
        *,
        expected_action: str | None = None,
        expected_resource: str | None = None,
        expected_session_id: str | None = None,
        expected_param_hash: str | None = None,
        expected_tenant_id: str | None = None,
    ) -> tuple[AuthorizationDecision, str]:
        """Enforce all scope restrictions on a token payload.

        Each restriction is only enforced when its corresponding
        ``expected_*`` parameter is provided (not None).  This allows
        callers to selectively enforce only the restrictions relevant
        to the current operation.

        Args:
            token_payload: Decoded JWT payload from the execution token.
            expected_action: If provided, the token's ``action`` claim must
                exactly match this value.
            expected_resource: If provided, the token's ``resource`` claim
                must exactly match this value, and the ``resource_hash``
                claim (if present) must also match the SHA-256 of this
                resource.
            expected_session_id: If provided, the token's ``session_id``
                claim must match this value.
            expected_param_hash: If provided, the token's ``param_hash``
                claim must exactly match this value.
            expected_tenant_id: If provided, the token's ``tenant_id``
                claim must be present, non-empty, and match this value.

        Returns:
            A tuple of (AuthorizationDecision, reason_string).
            Returns ALLOW with an explanatory message when all checks pass.
        """
        if expected_action is not None:
            token_action = token_payload.get("action")
            if token_action != expected_action:
                return AuthorizationDecision.DENY, (
                    f"Token action mismatch: expected {expected_action}, "
                    f"got {token_action}."
                )

        if expected_resource is not None:
            token_resource = token_payload.get("resource")
            if token_resource != expected_resource:
                return AuthorizationDecision.DENY, "Token resource mismatch."
            token_resource_hash = token_payload.get("resource_hash")
            if token_resource_hash is not None:
                expected_hash = self.compute_resource_hash(expected_resource)
                if str(token_resource_hash) != str(expected_hash):
                    return AuthorizationDecision.DENY, (
                        "Token resource hash mismatch - possible tampering detected."
                    )

        token_session_id = token_payload.get("session_id")
        if expected_session_id is not None and token_session_id != expected_session_id:
            return AuthorizationDecision.DENY, "Token session mismatch."

        token_param_hash = token_payload.get("param_hash")
        if expected_param_hash is not None:
            if str(token_param_hash) != str(expected_param_hash):
                return AuthorizationDecision.DENY, (
                    "Token parameter hash mismatch - parameter substitution detected."
                )

        if expected_tenant_id is not None:
            token_tenant = token_payload.get("tenant_id")
            if not token_tenant:
                return AuthorizationDecision.DENY, (
                    "Token missing tenant_id: cross-tenant token use denied."
                )
            if str(token_tenant) != str(expected_tenant_id):
                return AuthorizationDecision.DENY, (
                    "Token tenant mismatch - cross-tenant use detected."
                )

        return AuthorizationDecision.ALLOW, "Token scope valid."
