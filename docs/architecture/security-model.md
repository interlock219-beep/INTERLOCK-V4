# Security Model

Interlock's security model is built on default-deny authorization, tenant isolation, short-lived execution tokens, and fail-closed behavior.

## Authorization model

Authorization is evaluated deterministically in `AuthorizationService`:

1. **Tenant** — the request must carry a valid tenant identity (when `AUTHORIZATION_REQUIRE_TENANT=true`, the production default).
2. **Agent** — the acting agent must be registered and not quarantined/revoked.
3. **User** — the human principal (if any) must be authenticated.
4. **Service / Action / Resource** — evaluated against the policy engine.
5. **Expiration** — authority grants and tokens are time-bounded.
6. **Tool** — specific tools can be denied or require HITL.

The result is one of: `ALLOW`, `DENY`, or `REQUIRE_HITL`. Unknown actions are denied by default (`AUTHORIZATION_DEFAULT_DENY=true` in production).

## Policy engine

`CentralPolicyEngine` loads versioned YAML rules from `config/policies.yaml` with priority-based matching (effects: allow, deny, require_hitl). A legacy `PolicyEngine` provides regex-based text-risk matching with word boundaries and flexible whitespace.

## Tokens

Two distinct token types serve different purposes:

| Token | Algorithm | Purpose | Replay protection |
|-------|-----------|---------|-------------------|
| Access token | HS256 JWT | Authenticate users to protected routes | None (stateless; relies on short expiry) |
| Execution token | Ed25519 JWT | Authorize a single tool execution | Atomic nonce consumption (Redis) |

Execution tokens are short-lived (1–60 seconds, default 30), signed with Ed25519, and consumed exactly once via atomic nonce. If Redis is unavailable in production, nonce consumption **fails closed** — the execution is denied.

## Tenant isolation

Every major table carries a `tenant_id`. All repository queries filter by the authenticated user's tenant. Cross-tenant access is denied and explicitly tested (`tests/integration/test_cross_tenant_isolation.py`).

## Rate limiting

`RateLimitMiddleware` uses a process-local sliding window, with a Redis-backed distributed option. It is an availability control, not a distributed security boundary. Configurable per route category (login, register, intent, recovery).

## Network and input security

- **SQL injection** — `sqlglot` parser for destructive-operation detection; table whitelist + column regex + parameterized values at the adapter level.
- **Path traversal** — `..` component rejection in key directory and tool-argument validation.
- **SSRF** — URL scheme restriction, private/loopback/reserved IP blocking, DNS resolution checks.
- **Shell injection** — metacharacter detection in tool arguments.
- **Request size** — configurable limit (default 1 MiB).
- **CORS** — origin allowlist.
- **Security headers** — baseline response headers middleware.

## Audit

JSONL audit events with correlation IDs. Tool arguments and execution tokens are deliberately **not** written to audit records. Compliance exports are HMAC-signed.

## Key management

Ed25519 keys are generated in-process by default. `EXECUTION_KEY_PATH` persists keys across restarts. `KMSKeyManager` and `HSMKeyProvider` are interface placeholders — production deployments must integrate external key management.

## Security boundaries

- Intent endpoints (`/intent/verify`, `/intent/execute`) require bearer-token authentication.
- HITL approval requests are durably persisted in PostgreSQL and survive restarts.
- Rate-limit counters are process-local and lost on restart (availability control, not security boundary).
- The SDK validates gateway URLs as HTTP(S) but does not perform network-level access control.

## What is not claimed

- No independent penetration testing by a qualified security firm.
- No SOC 2, HIPAA, PCI-DSS, or regulatory compliance certification.
- Testing evidence does not equal certification.
