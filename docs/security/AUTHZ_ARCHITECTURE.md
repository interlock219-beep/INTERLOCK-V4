# Interlock V4 Authorization Architecture

**Document:** Authorization architecture, identity management, and access control design for Interlock V4.
**Status:** Reflects the current codebase as of 2026-08-21.

---

## 1. Identity and Access Management Overview

Interlock V4 authenticates users via HS256 JWT access tokens and authorizes actions via an explicit `AuthorizationService`. The system does not currently delegate authentication to an external identity provider. Authentication and authorization are enforced at the API layer through FastAPI dependencies.

| Layer | Mechanism |
|-------|-----------|
| Authentication | HS256 JWT access tokens (`type=access`) issued on registration and login |
| Session | Stateless bearer tokens; no server-side session state |
| Authorization | Explicit `AuthorizationService` evaluating tenant, agent, user, service, action, resource, and tool identities |
| Privileged actions | Role checks (`admin`, `operator`) on specific endpoints via `require_hitl_approver` and inline `current_user.role` checks |

**Implementation Status:** Implemented (core). Enterprise SSO, OIDC, SAML, and SCIM are configured as adapter interfaces but are not active production integrations.

---

## 2. RBAC Model

Roles are stored as a string field on the `User` entity (`role`, default `viewer`). The current role set is:

| Role | Description | Usage |
|------|-------------|-------|
| `viewer` | Default role assigned at registration. | Assigned to all newly registered users. No explicit endpoint restrictions beyond authentication. |
| `operator` | Elevated role. | Included in `hitl_approver_roles` (default: `["admin", "operator"]`). Operators can approve or reject HITL requests. |
| `admin` | Administrative role. | Included in `hitl_approver_roles`. Required for `/metrics/security` and `/compliance/evidence` endpoints. |

### Role Enforcement Points

- **HITL approver gate** (`require_hitl_approver`): Checks `current_user.role in settings.hitl_approver_roles`. Returns 403 if the role is not in the configured set.
- **Security metrics** (`/metrics/security`): Inline `if current_user.role != "admin"` check. Returns 403.
- **Compliance evidence export** (`/compliance/evidence`): Inline `if current_user.role != "admin"` check. Returns 403.

### Role Assignment

- New users are assigned `role="viewer"` at registration (`RegisterUserUseCase`).
- Role changes are not exposed through any API endpoint in V4. Role mutation requires direct database modification or integration with an external IAM system.

**Implementation Status:** Partial. RBAC exists with three roles and is enforced on HITL, metrics, and compliance endpoints. There is no comprehensive role-based permission matrix enforced across all intent and approval operations. Role mutation is not self-service.

---

## 3. Permission System Design

Permissions are currently enforced through a combination of:

1. **Authentication gate** (`CurrentUser` dependency): All protected endpoints require a valid bearer token. Invalid or missing tokens return 401.
2. **Role checks**: Inline `current_user.role` comparisons on specific endpoints.
3. **AuthorizationService settings**: Configurable allowlists and denylists for services, actions, resources, and tools:
   - `authorization_denied_tools` — tools that always return DENY
   - `authorization_hitl_tools` — tools that always return REQUIRE_HITL
   - `authorization_allowed_services` — if set, only these service IDs are permitted
   - `authorization_allowed_actions` — if set, only these actions are permitted
   - `authorization_allowed_resources` — if set, only these resources are permitted
   - `authorization_expiry_seconds` — authorization decisions expire after this duration (default 3600s)
4. **HITL approver roles**: `hitl_approver_roles` setting controls who can approve/reject HITL requests.

There is no separate permission entity or fine-grained permission matrix. Permissions are implicit in the settings allowlists/denylists and role strings.

**Implementation Status:** Partial. Permission enforcement exists via `AuthorizationService` and role checks but is not a full RBAC permission matrix. Permission management is settings-driven rather than policy-driven.

---

## 4. Default-Deny vs Default-Allow Posture

The `AuthorizationService.authorize()` method evaluates checks in order from most restrictive to least restrictive. If a check returns `DENY`, that decision is returned immediately. If all checks pass, the decision is `ALLOW`.

The posture is **default-allow** for backward compatibility:

- If `authorization_require_tenant` is `False` (default), tenant absence does not cause denial.
- If `authorization_allowed_services` is `None` (default), any service ID is permitted.
- If `authorization_allowed_actions` is `None` (default), any action is permitted.
- If `authorization_allowed_resources` is `None` (default), any resource is permitted.
- If `authorization_denied_tools` is empty (default), no tools are denied by the authorization service.
- If `authorization_hitl_tools` is empty (default), no tools are forced to HITL by the authorization service.

The documentation explicitly states: "Defaults are permissive for backward compatibility; production deployments should configure explicit restrictions via settings."

**Implementation Status:** Partial. The `AuthorizationService` supports default-deny via settings configuration, but defaults are permissive. Production deployments must explicitly configure restrictions.

---

## 5. Action-Level Authorization

The `AuthorizationContext` includes an `action` field (default `"execute"`). The `AuthorizationService._check_action()` method evaluates this against `authorization_allowed_actions`:

```python
def _check_action(self, context: AuthorizationContext) -> AuthorizationDecision:
    allowed_actions = getattr(self._settings, "authorization_allowed_actions", None)
    if allowed_actions is not None:
        if not context.action:
            return AuthorizationDecision.DENY
        if context.action not in allowed_actions:
            return AuthorizationDecision.DENY
    return AuthorizationDecision.ALLOW
```

If `authorization_allowed_actions` is configured, only listed actions are permitted. The action is propagated through the intent verification flow via `AgentActionDAG.action`.

**Implementation Status:** Partial. Action-level authorization is implemented in `AuthorizationService` but defaults to permissive. It is not enforced at every endpoint independently of settings configuration.

---

## 6. Resource-Level Authorization

The `AuthorizationContext` includes a `resource` field (default `""`). The `AuthorizationService._check_resource()` method evaluates this against `authorization_allowed_resources`:

```python
def _check_resource(self, context: AuthorizationContext) -> AuthorizationDecision:
    allowed_resources = getattr(self._settings, "authorization_allowed_resources", None)
    if allowed_resources is not None:
        if not context.resource:
            return AuthorizationDecision.DENY
        if context.resource not in allowed_resources:
            return AuthorizationDecision.DENY
    return AuthorizationDecision.ALLOW
```

If `authorization_allowed_resources` is configured, only listed resources are permitted.

**Implementation Status:** Partial. Resource-level authorization is implemented in `AuthorizationService` but defaults to permissive.

---

## 7. Tenant Isolation in Authorization

The `AuthorizationService._check_tenant()` method enforces tenant identity when `authorization_require_tenant` is enabled:

```python
def _check_tenant(self, context: AuthorizationContext) -> AuthorizationDecision:
    require_tenant = getattr(self._settings, "authorization_require_tenant", False)
    if not require_tenant:
        return AuthorizationDecision.ALLOW
    if not context.tenant_id:
        return AuthorizationDecision.DENY
    if not self._is_valid_tenant(context.tenant_id):
        return AuthorizationDecision.DENY
    return AuthorizationDecision.ALLOW
```

Tenant validation checks that `tenant_id` is non-empty, non-whitespace, and at most 64 characters. The `AuthorizationContext` carries `tenant_id` from `AgentActionDAG` through the verification flow.

The `HITLQueue` enforces tenant boundaries on approval decisions:
- `list_pending_requests(tenant_id=...)` filters by tenant.
- `_decide()` raises `ApprovalError` if the request's `tenant_id` does not match the caller's `tenant_id`.

**Implementation Status:** Partial. Tenant authorization is implemented but defaults to disabled (`authorization_require_tenant=False`). Tenant enforcement in HITL is present but optional.

---

## 8. Privileged Access Controls

Privileged actions are protected by role checks:

| Endpoint | Privilege | Enforcement |
|----------|-----------|-------------|
| `/approval/*` | HITL approver | `require_hitl_approver` dependency checking `hitl_approver_roles` |
| `/metrics/security` | Admin | Inline `current_user.role != "admin"` check |
| `/compliance/evidence` | Admin | Inline `current_user.role != "admin"` check |

There is no break-glass, just-in-time (JIT) access, or privileged session monitoring in V4.

**Implementation Status:** Partial. Basic role-based privilege gates exist on specific endpoints. No JIT, break-glass, or privileged session controls.

---

## 9. Administrative Controls

Administrative capabilities in V4 are limited to:

- Viewing security metrics (`/metrics/security`, admin-only)
- Exporting compliance evidence (`/compliance/evidence`, admin-only)
- Approving/rejecting HITL requests (admin and operator roles)
- Manual database modifications for role changes (no admin API)

There is no admin API for user lifecycle management, policy management, or key management in V4. These operations require direct database or configuration access.

**Implementation Status:** Partial. Administrative endpoints exist for metrics and compliance export. No admin API for user, policy, or key management.

---

## 10. Session Security

Sessions are stateless. Each login or registration issues a new HS256 JWT access token with:

- `sub`: user UUID
- `email`: user email
- `iat`: issued-at timestamp
- `nbf`: not-before timestamp
- `exp`: expiration timestamp (default 30 minutes)
- `jti`: unique JWT ID
- `type`: `"access"`

Token validation includes:
- Signature verification (HS256)
- Required claims enforcement (`sub`, `email`, `exp`, `iat`, `jti`)
- `nbf` verification
- `type` must equal `"access"`
- Clock skew tolerance (default 30 seconds)

There is no server-side token revocation list, session invalidation API, or concurrent session limit. Token expiration is the only lifecycle control.

**Implementation Status:** Partial. JWT tokens are validated with standard claims and short expiration. No server-side revocation or session management exists.

---

## 11. Account Lifecycle

### Registration
- Endpoint: `POST /api/v1/auth/register`
- Creates a user with `role="viewer"`, `is_active=True`
- Optional `tenant_id` from request payload
- Issues an access token immediately
- Password must meet strength requirements (min 12 chars, upper, lower, digit, special)
- Bcrypt hashing with configurable rounds (default 12, range 10-15)
- Duplicate email rejection (409 Conflict)

### Activation
- Users are created as `is_active=True` by default
- The `AuthenticateUserUseCase` rejects inactive users with `InactiveUserError` (401)
- There is no registration activation flow (email verification, admin approval) in V4

### Deactivation
- There is no API endpoint to deactivate a user in V4
- Deactivation requires direct database modification
- Inactive users cannot log in (`AuthenticateUserUseCase` checks `is_active`)

### Deletion
- There is no user deletion API in V4
- Account deletion requires direct database modification

### Password Management
- No password change or reset API in V4
- Password reset requires direct database modification

**Implementation Status:** Partial. Registration and login are implemented. Activation, deactivation, deletion, and password management require direct database access or are absent.

---

## 12. Enterprise SSO, OIDC, SAML, MFA, SCIM Preparation

### IAM Adapter Interface

The codebase defines an `IAMAdapter` abstract base class and three concrete adapters:

| Adapter | Status | Description |
|---------|--------|-------------|
| `MockIAMAdapter` | Implemented | In-memory mock for testing |
| `SAMLIAMAdapter` | Partial | Class exists, accepts SAML config, but no actual SAML flow integration |
| `OIDCIAMAdapter` | Partial | Class exists, accepts OIDC config, but no actual OIDC flow integration |
| `SCIMAdapter` | Partial | Class exists, implements `provision_user`/`deprovision_user` with SCIM-style payloads, but no actual SCIM endpoint integration |

Settings for these adapters are defined in `Settings`:
- `iam_enabled` (default `False`)
- `iam_provider` (default `"mock"`)
- `saml_entity_id`, `saml_sso_url`, `saml_x509_cert`
- `oidc_client_id`, `oidc_client_secret`
- `scim_base_url`, `scim_token`

The `get_iam_adapter()` factory routes to the appropriate adapter based on `iam_provider`.

### MFA

No MFA implementation exists in V4. There are no settings, adapters, or UI flows for MFA.

**Implementation Status:** Planned for SSO/OIDC/SAML/MFA/SCIM. Adapter stubs exist but are not integrated with production identity providers. No MFA support.

---

## 13. Implementation Status Summary

| Component | Status | Notes |
|-----------|--------|-------|
| JWT access tokens | Implemented | HS256, standard claims, type validation, clock skew |
| Ed25519 execution tokens | Implemented | Atomic nonce consumption, strict expiry |
| RBAC roles (viewer, operator, admin) | Partial | Enforced on HITL, metrics, compliance; no comprehensive matrix |
| Permission system | Partial | Settings-driven allowlists/denylists; no fine-grained policy |
| Default-deny posture | Partial | Supported via settings but defaults are permissive |
| Default-allow posture | Implemented | Default state before explicit configuration |
| Action-level authorization | Partial | Implemented in `AuthorizationService`; defaults permissive |
| Resource-level authorization | Partial | Implemented in `AuthorizationService`; defaults permissive |
| Tenant authorization | Partial | Implemented but disabled by default (`authorization_require_tenant=False`) |
| Privileged access controls | Partial | Role checks on specific endpoints; no JIT or break-glass |
| Administrative controls | Partial | Metrics and compliance endpoints; no admin API for users/policy/keys |
| Session security | Partial | Stateless JWT with short expiry; no revocation or session management |
| Account registration | Implemented | Email+password, bcrypt, strength validation, tenant_id optional |
| Account activation | Partial | Users created active; no email verification or admin approval flow |
| Account deactivation | Planned | No API; requires direct DB modification |
| Account deletion | Planned | No API; requires direct DB modification |
| Password management | Planned | No change or reset API |
| SSO integration | Planned | Adapter stubs exist; no production integration |
| OIDC integration | Planned | Adapter stub exists; no production integration |
| SAML integration | Planned | Adapter stub exists; no production integration |
| MFA | Planned | No implementation |
| SCIM provisioning | Planned | Adapter stub exists; no production integration |

---

## 14. Related Documentation

- [`docs/architecture/ARCHITECTURE.md`](docs/architecture/ARCHITECTURE.md) — Trust boundaries, request flow, attack paths
- [`docs/security/SECURITY_ASSURANCE_REPORT.md`](docs/security/SECURITY_ASSURANCE_REPORT.md) — Security controls, test evidence, findings
- [`docs/security/TENANT_ISOLATION.md`](docs/security/TENANT_ISOLATION.md) — Multi-tenant data model and isolation enforcement
- [`docs/operations/INCIDENT_RESPONSE.md`](docs/operations/INCIDENT_RESPONSE.md) — Security incident response procedures
