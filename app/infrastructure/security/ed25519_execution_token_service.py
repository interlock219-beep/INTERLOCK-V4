import base64
import hashlib
import json
import logging
import time
from typing import Any
from uuid import uuid4

import jwt
from cryptography.hazmat.primitives import serialization

from app.application.interfaces.execution_token_service import ExecutionTokenService
from app.application.interfaces.key_manager import KeyManager
from app.application.interfaces.nonce_store import NonceStore
from app.domain.exceptions.domain_errors import ExecutionTokenError

logger = logging.getLogger(__name__)


def _b64url_encode(data: bytes) -> str:
    """Base64url-encode without padding (RFC 7515)."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


_MAX_TENANT_ID_LENGTH = 64


class Ed25519ExecutionTokenService(ExecutionTokenService):
    """Ed25519-signed ephemeral execution tokens with replay protection and scope enforcement.

    Tokens are signed with Ed25519 (EdDSA) and include a JTI (nonce) that
    is atomically consumed via the NonceStore to prevent replay attacks.

    Scope restrictions enforced on verification:
        - Action restriction (Feature 16): token ``action`` claim must match
          the expected action.
        - Resource restriction with tamper detection (Feature 17): token
          ``resource`` claim must exactly match expected resource, and the
          ``resource_hash`` claim (SHA-256 of the resource) must also match
          if present.
        - Session restriction (Feature 18): if the token contains a
          ``session_id`` claim, the referenced session must be active.
        - Tenant restriction (Feature 19): cross-tenant token use is denied
          with clear error messages; tenant_id format is validated.
        - Parameter binding (Feature 20): if ``expected_param_hash`` is
          provided, it must exactly match the token's ``param_hash`` claim
          to prevent parameter substitution attacks.

    Key rotation support:
        - Each token carries a ``kid`` header identifying the signing key.
        - Verification selects the correct key from the KeyManager by
          ``kid``.  Tokens without ``kid`` fall back to the active key
          (backward compatibility).
        - JWKS returns all currently valid keys (active + previous) so
          clients can verify tokens signed with any still-valid key.
    """

    def __init__(
        self,
        *,
        key_manager: KeyManager,
        nonce_store: NonceStore,
        clock_skew_seconds: int = 30,
    ) -> None:
        self._key_manager = key_manager
        self._nonce_store = nonce_store
        self._clock_skew_seconds = clock_skew_seconds

    @staticmethod
    def _validate_tenant_id(tenant_id: str) -> None:
        """Validate tenant_id format.

        Args:
            tenant_id: The tenant identifier to validate.

        Raises:
            ValueError: If tenant_id is empty, whitespace-only, or exceeds
                the maximum allowed length.
        """
        if not tenant_id or not str(tenant_id).strip():
            raise ValueError("tenant_id must be a non-empty string.")
        if len(str(tenant_id)) > _MAX_TENANT_ID_LENGTH:
            raise ValueError(f"tenant_id must be at most {_MAX_TENANT_ID_LENGTH} characters.")

    @staticmethod
    def compute_resource_hash(resource: str) -> str:
        """Compute a SHA-256 tamper-evident hash of a resource path.

        Args:
            resource: The resource path to hash.

        Returns:
            Hex-encoded SHA-256 digest of the resource string.
        """
        return hashlib.sha256(resource.encode("utf-8")).hexdigest()

    @staticmethod
    def compute_param_hash(params: dict[str, Any]) -> str:
        """Compute a canonical SHA-256 hash of a parameter set.

        Parameters are sorted by key to ensure deterministic hashing
        regardless of insertion order.

        Args:
            params: Dictionary of parameters to hash.

        Returns:
            Hex-encoded SHA-256 digest of the canonical parameter set.
        """
        canonical = sorted(str(k) for k in params)
        return hashlib.sha256(str(canonical).encode("utf-8")).hexdigest()

    def create_execution_token(
        self,
        *,
        agent_id: str,
        tool: str,
        ttl_seconds: int,
        subject: str | None = None,
        tenant_id: str | None = None,
        audience: str | None = None,
        resource: str | None = None,
        action: str | None = None,
        session_id: str | None = None,
        param_hash: str | None = None,
        resource_hash: str | None = None,
    ) -> str:
        now = int(time.time())
        key_id = self._key_manager.active_key_id
        header = {"alg": "EdDSA", "typ": "JWT", "kid": key_id}
        payload: dict[str, Any] = {
            "sub": subject or agent_id,
            "agent_id": agent_id,
            "type": "execution",
            "tool": tool,
            "iat": now,
            "nbf": now,
            "exp": now + ttl_seconds,
            "jti": str(uuid4()),
        }
        if tenant_id is not None:
            self._validate_tenant_id(tenant_id)
            payload["tenant_id"] = tenant_id
        if audience is not None:
            payload["aud"] = audience
        if resource is not None:
            payload["resource"] = resource
        if action is not None:
            payload["action"] = action
        if session_id is not None:
            payload["session_id"] = session_id
        if param_hash is not None:
            payload["param_hash"] = param_hash
        if resource_hash is not None:
            payload["resource_hash"] = resource_hash

        header_segment = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("ascii"))
        payload_segment = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("ascii"))
        signing_input = f"{header_segment}.{payload_segment}".encode("ascii")

        signature = self._key_manager.sign(signing_input, key_id)
        signature_segment = _b64url_encode(signature)

        return f"{header_segment}.{payload_segment}.{signature_segment}"

    def verify_execution_token(
        self,
        token: str,
        *,
        expected_tenant_id: str | None = None,
        expected_audience: str | None = None,
        expected_resource: str | None = None,
        expected_action: str | None = None,
        expected_session_id: str | None = None,
        expected_param_hash: str | None = None,
    ) -> dict[str, Any]:
        return self._verify_execution_token_internal(
            token,
            expected_tenant_id=expected_tenant_id,
            expected_audience=expected_audience,
            expected_resource=expected_resource,
            expected_action=expected_action,
            expected_session_id=expected_session_id,
            expected_param_hash=expected_param_hash,
            consume_nonce=True,
        )

    def _verify_execution_token_internal(
        self,
        token: str,
        *,
        expected_tenant_id: str | None = None,
        expected_audience: str | None = None,
        expected_resource: str | None = None,
        expected_action: str | None = None,
        expected_session_id: str | None = None,
        expected_param_hash: str | None = None,
        consume_nonce: bool = True,
    ) -> dict[str, Any]:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError:
            raise ExecutionTokenError("Invalid or expired execution token.") from None

        kid = header.get("kid")

        try:
            if kid is not None:
                verify_key = self._key_manager.get_verification_key(kid)
            else:
                verify_key = self._key_manager.get_verification_key()
        except KeyError:
            raise ExecutionTokenError("Unknown key ID.") from None

        try:
            payload = jwt.decode(
                token,
                verify_key,
                algorithms=["EdDSA"],
                options={
                    "require": ["sub", "type", "tool", "exp", "iat", "jti"],
                    "verify_nbf": True,
                    "verify_aud": False,
                    "verify_exp": False,
                },
                leeway=self._clock_skew_seconds,
            )
        except jwt.PyJWTError as exc:
            raise ExecutionTokenError("Invalid or expired execution token.") from exc

        if payload.get("type") != "execution":
            raise ExecutionTokenError("Invalid token type.")

        nonce = str(payload.get("jti", ""))
        if not nonce:
            raise ExecutionTokenError("Missing token nonce.")

        if int(payload["exp"]) < int(time.time()):
            raise ExecutionTokenError("Execution token has expired.")

        token_tenant_id = payload.get("tenant_id")
        if token_tenant_id is not None and not str(token_tenant_id).strip():
            raise ExecutionTokenError(
                "Token missing tenant_id: tenant_id must be a non-empty string."
            )
        if expected_tenant_id is not None:
            if not token_tenant_id:
                raise ExecutionTokenError("Token missing tenant_id: cross-tenant token use denied.")
            if str(token_tenant_id) != str(expected_tenant_id):
                raise ExecutionTokenError(
                    "Token tenant_id mismatch: cross-tenant token use detected and denied."
                )
            self._validate_tenant_id(str(expected_tenant_id))

        if expected_audience is not None and payload.get("aud") != expected_audience:
            raise ExecutionTokenError("Token audience mismatch.")
        if expected_resource is not None and payload.get("resource") != expected_resource:
            raise ExecutionTokenError("Token resource mismatch.")

        token_resource_hash = payload.get("resource_hash")
        if expected_resource is not None and token_resource_hash is not None:
            expected_resource_hash = self.compute_resource_hash(expected_resource)
            if str(token_resource_hash) != str(expected_resource_hash):
                raise ExecutionTokenError(
                    "Token resource hash mismatch - possible tampering detected."
                )

        if expected_action is not None:
            token_action = payload.get("action")
            if token_action != expected_action:
                raise ExecutionTokenError(
                    f"Token action mismatch: expected {expected_action}, got {token_action}."
                )

        token_session_id = payload.get("session_id")
        if expected_session_id is not None and token_session_id != expected_session_id:
            raise ExecutionTokenError("Token session mismatch.")

        if expected_param_hash is not None:
            token_param_hash = payload.get("param_hash")
            if str(token_param_hash) != str(expected_param_hash):
                raise ExecutionTokenError(
                    "Token parameter hash mismatch - parameter substitution detected."
                )

        ttl_seconds = max(int(payload["exp"]) - int(time.time()), 1)
        if consume_nonce:
            if not self._nonce_store.consume(nonce, ttl_seconds):
                raise ExecutionTokenError("Token has already been used.")
        else:
            if self._nonce_store.is_consumed(nonce):
                raise ExecutionTokenError("Token has already been used.")

        return payload

    def peek_execution_token(
        self,
        token: str,
        *,
        expected_tenant_id: str | None = None,
        expected_audience: str | None = None,
        expected_resource: str | None = None,
        expected_action: str | None = None,
        expected_session_id: str | None = None,
        expected_param_hash: str | None = None,
    ) -> dict[str, Any]:
        return self._verify_execution_token_internal(
            token,
            expected_tenant_id=expected_tenant_id,
            expected_audience=expected_audience,
            expected_resource=expected_resource,
            expected_action=expected_action,
            expected_session_id=expected_session_id,
            expected_param_hash=expected_param_hash,
            consume_nonce=False,
        )

    def get_jwks(self) -> dict[str, Any]:
        keys: list[dict[str, Any]] = []
        for kid in self._key_manager.get_key_ids():
            public_key = self._key_manager.get_verification_key(kid)
            public_bytes = public_key.public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
            keys.append(
                {
                    "kty": "OKP",
                    "kid": kid,
                    "crv": "Ed25519",
                    "x": base64.urlsafe_b64encode(public_bytes).rstrip(b"=").decode("ascii"),
                    "use": "sig",
                    "alg": "EdDSA",
                }
            )
        return {"keys": keys}
