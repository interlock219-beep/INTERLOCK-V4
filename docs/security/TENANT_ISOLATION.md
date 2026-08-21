# IntentLock Tenant Isolation

**Document:** Multi-tenant data model, isolation enforcement, and boundary controls for IntentLock V4.
**Status:** Reflects the current codebase as of 2026-08-21.

---

## 1. Multi-Tenant Data Model

Tenant isolation in IntentLock is implemented at the application and database schema level. The tenant identifier (`tenant_id`, String(64), nullable) is stored on the following tables:

| Table | Column | Nullable | Indexed | Description |
|-------|--------|----------|---------|-------------|
| `users` | `tenant_id` | Yes | Yes | Tenant assignment for each user |
| `approval_requests` | `tenant_id` | Yes | Yes | Tenant assignment for each HITL request |

The `tenant_id` is propagated through the application layer:

- `User` entity: `tenant_id: str | None`
- `UserResponse` DTO: `tenant_id: str | None`
- `AgentActionDAG` intent model: `tenant_id: str | None`
- `AuthorizationContext` value object: `tenant_id: str | None`
- `ApprovalRequestModel` ORM: `tenant_id: str | None`

During registration, `tenant_id` is accepted from the request payload and persisted on the new user record.

**Implementation Status:** Implemented. Schema includes `tenant_id` on `users` and `approval_requests` with indexes.

---

## 2. Tenant Identification and Enforcement

### Identification

Tenant identity originates from the client-supplied `tenant_id` field in the intent verification request payload (`AgentActionDAG.tenant_id`). This value is carried through to:

- `AuthorizationContext.tenant_id` for the `AuthorizationService` evaluation
- `HITLQueue` for request enqueueing and decision enforcement
- Audit and compliance records

There is no server-side tenant resolution from authentication context (e.g., mapping `sub` to a tenant). The tenant is trusted from the request payload.

### Enforcement

Tenant enforcement is controlled by the `authorization_require_tenant` setting (default: `False`). When enabled, the `AuthorizationService._check_tenant()` method:

1. Requires `tenant_id` to be present in the `AuthorizationContext`
2. Validates that `tenant_id` is non-empty, non-whitespace, and at most 64 characters
3. Returns `DENY` if either check fails

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

**Implementation Status:** Partial. Tenant enforcement logic exists but is disabled by default. Production deployments must explicitly set `authorization_require_tenant=True`.

---

## 3. Cross-Tenant Access Prevention

### HITL Approval Boundaries

The `HITLQueue` enforces tenant boundaries on approval decisions:

- `_decide()` raises `ApprovalError` if the approval request's `tenant_id` does not match the caller-supplied `tenant_id`
- `list_pending_requests(tenant_id=...)` filters pending requests by tenant

```python
if tenant_id is not None and model.tenant_id != tenant_id:
    raise ApprovalError(
        f"Approval request {request_id} does not belong to tenant {tenant_id}"
    )
```

**Note:** The `/approval/*` endpoints do not currently extract `tenant_id` from the authenticated user's context. The `tenant_id` used in the boundary check must be supplied by the caller in the request path or body, which is a known limitation.

### Authorization Check Boundaries

The `AuthorizationService` checks tenant identity as the first evaluation step (most restrictive). If tenant enforcement is enabled and the tenant is invalid, the decision is `DENY` before any other checks are evaluated.

### Missing Enforcement

The following cross-tenant access vectors are **not** currently enforced:

- `UserRepository.get_by_id()` does not filter by tenant. Any authenticated user can query any user by ID.
- `UserRepository.get_by_email()` does not filter by tenant.
- Audit log queries do not enforce tenant scoping.
- The `/auth/me` endpoint returns the current user's profile, which includes their `tenant_id`, but there is no tenant-scoped user listing API.

**Implementation Status:** Partial. HITL tenant boundaries are enforced. Cross-tenant access prevention is not comprehensive across all data access paths.

---

## 4. Database-Level Isolation

### Schema-Level Isolation

Tenant columns are present on `users` and `approval_requests` tables. Alembic migration `0003_add_tenant_id` added these columns and created non-unique indexes.

### Application-Level Isolation

The application uses SQLAlchemy ORM. Queries are constructed at the application layer. There is no PostgreSQL Row-Level Security (RLS) policy configured in V4. All tenant filtering is performed in application code.

### Repository Methods

| Method | Tenant Filter | Description |
|--------|--------------|-------------|
| `get_by_id(user_id)` | No | Returns user by UUID regardless of tenant |
| `get_by_email(email)` | No | Returns user by email regardless of tenant |
| `get_by_tenant(tenant_id)` | Yes | Returns all users for a tenant |
| `save(user)` | No | Saves/updates user; preserves `tenant_id` from entity |
| `exists_by_email(email)` | No | Checks email existence regardless of tenant |

**Implementation Status:** Partial. Tenant columns and indexes exist. Application-level tenant filtering is present in `get_by_tenant` and HITL operations but absent in `get_by_id`, `get_by_email`, and `exists_by_email`.

---

## 5. Redis Key Namespacing

Redis is used for two purposes in V4:

1. **Nonce store** (`CompositeNonceStore`): Stores execution token JTIs for replay protection. Keys are not tenant-namespaced.
2. **HITL cache** (`HITLQueue`): Caches pending approval requests for fast lookup. Keys use the format `hitl:{request_key}` without tenant prefix.

```python
self._redis_client.set(
    f"hitl:{request_key}",
    str({"request_id": request_key, "status": "pending", "tenant_id": tenant_id}),
    ex=self._ttl_seconds,
)
```

There is no systematic tenant-based key namespacing in Redis. The `tenant_id` is embedded in the cached value but not in the key itself.

**Implementation Status:** Partial. Redis is used for nonce storage and HITL caching. No tenant-based key namespacing is implemented.

---

## 6. Audit Log Tenant Segregation

Audit events are written to a single JSONL file (`logs/audit_trail.jsonl`). Each record may include a `tenant_id` field when the originating operation includes tenant context:

- Policy rules include `tenant_id` in compliance evidence export
- HITL approval/rejection events include `tenant_id` in the `HITLQueue` cache value
- Intent verification events do not currently include `tenant_id` in the audit record

There is no tenant-based log segregation (separate files, directories, or indices per tenant). All tenants' events are interleaved in the same log stream.

**Implementation Status:** Partial. Tenant context is included in some records (compliance evidence, HITL cache). Intent verification audit records do not include `tenant_id`. No per-tenant log segregation.

---

## 7. Tenant Admin Boundaries

Tenant administration is not a first-class concept in V4. There is no:

- Tenant admin role separate from global roles
- Tenant-scoped user management API
- Tenant-level policy configuration
- Tenant admin boundary enforcement in the authorization service

The `AuthorizationService._is_valid_tenant()` method validates tenant ID format but does not check whether the caller is authorized to act on behalf of that tenant.

**Implementation Status:** Planned. No tenant admin boundaries are implemented.

---

## 8. Testing Strategy for Tenant Isolation

### Existing Tests

- `tests/unit/test_authorization_service.py`: Tests `AuthorizationService` including tenant checks when `authorization_require_tenant=True`
- `tests/unit/test_hitl_queue.py`: Tests `HITLQueue` including tenant boundary enforcement in `_decide()`
- `tests/unit/test_authorization_api.py`: Integration tests for authorization endpoints

### Coverage Gaps

- No tests for cross-tenant access prevention via `get_by_id` or `get_by_email`
- No tests for tenant-scoped audit log queries
- No tests for Redis key namespace isolation
- No tests for tenant data leakage between users in the same database

### Recommended Test Additions

1. Verify that `get_by_id` cannot retrieve users from other tenants (once tenant filtering is added)
2. Verify that `get_by_email` cannot retrieve users from other tenants (once tenant filtering is added)
3. Verify that approval requests from tenant A cannot be listed or decided by tenant B
4. Verify that Redis keys for tenant A are not accessible to tenant B
5. Verify that audit records contain `tenant_id` for all tenant-scoped operations
6. Verify that `authorization_require_tenant=True` denies requests without `tenant_id`
7. Verify that invalid `tenant_id` formats are rejected

**Implementation Status:** Partial. Unit tests exist for `AuthorizationService` and `HITLQueue` tenant checks. Cross-tenant access prevention tests are absent.

---

## 9. Known Limitations

1. **Tenant enforcement disabled by default:** `authorization_require_tenant=False`. Multi-tenant deployments must explicitly enable this setting.
2. **No server-side tenant resolution:** Tenant identity is trusted from the client-supplied request payload. There is no mapping from authenticated user to tenant.
3. **Incomplete repository-level filtering:** `get_by_id`, `get_by_email`, and `exists_by_email` do not filter by tenant.
4. **No database RLS:** PostgreSQL Row-Level Security is not configured. Tenant isolation relies entirely on application-level query filtering.
5. **No Redis tenant namespacing:** Redis keys for nonces and HITL cache do not include tenant prefix.
6. **No per-tenant log segregation:** All audit events are written to a single JSONL file.
7. **No tenant admin boundaries:** No tenant-scoped administration capabilities.
8. **Tenant ID length:** Limited to 64 characters in the database schema.
9. **Tenant ID format:** No format validation beyond non-empty and length. UUID, domain, or custom formats are accepted.

---

## 10. Related Documentation

- [`docs/architecture/ARCHITECTURE.md`](docs/architecture/ARCHITECTURE.md) — Trust boundaries, request flow
- [`docs/security/AUTHZ_ARCHITECTURE.md`](docs/security/AUTHZ_ARCHITECTURE.md) — Authorization architecture and RBAC model
- [`docs/security/SECURITY_ASSURANCE_REPORT.md`](docs/security/SECURITY_ASSURANCE_REPORT.md) — Security controls and test evidence
- [`docs/operations/INCIDENT_RESPONSE.md`](docs/operations/INCIDENT_RESPONSE.md) — Security incident response procedures
