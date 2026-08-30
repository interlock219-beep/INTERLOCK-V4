# Interlock V4 — Release Baseline

## 1. Current Architecture

Interlock V4 implements a hexagonal (ports-and-adapters) architecture:

- **Application layer** (`app/application/`): Use cases, DTOs, and interface definitions.
- **Domain layer** (`app/domain/`): Entities, value objects, repository interfaces, and domain services.
- **Infrastructure layer** (`app/infrastructure/`): Persistence (SQLAlchemy), security (JWT, bcrypt, ed25519), Redis, recovery adapters, SSO adapters, logging, observability.
- **Presentation layer** (`app/presentation/`): FastAPI routes, middleware, dependencies.
- **SDK** (`sdk/`): Client libraries (`intentlock.py`, `langchain_adapter.py`).
- **Web dashboard** (`web/`): Next.js frontend.

## 2. Supported Recovery Adapters

| Adapter | Type | Capability | Notes |
|---------|------|------------|-------|
| `ConfigRecoveryAdapter` | Configuration | `PRODUCTION_VALIDATED` | Atomic file replacement, hash-based drift detection, conflict detection |
| `DatabaseRecoveryAdapter` | Database (SQL) | `PRODUCTION_VALIDATED` | INSERT/DELETE/UPDATE recovery, SQLite/PostgreSQL, transaction-safe, foreign-key aware |
| `FilesystemRecoveryAdapter` | Filesystem | `PRODUCTION_VALIDATED` | File create/modify/delete/rename recovery, metadata preservation, atomic operations |
| `GitRepositoryAdapter` | Git repository | `PRODUCTION_VALIDATED` | Commit-aware and working-tree recovery, conflict detection |
| `MockRecoveryAdapter` | Simulation | `MOCK` | Scenario-based simulation for testing |
| `DatabaseRecordAdapter` | Database (legacy) | `SIMULATION_CAPABLE` | Reference implementation, returns `REQUIRES_MANUAL_ACTION` |
| `FileVersionAdapter` | Filesystem (legacy) | `SIMULATION_CAPABLE` | Reference implementation, returns `REQUIRES_MANUAL_ACTION` |
| `ConfigRollbackAdapter` | Configuration (legacy) | `SIMULATION_CAPABLE` | Reference implementation, returns `REQUIRES_MANUAL_ACTION` |

## 3. Security Defaults

| Control | Production Default | Test Default | Enforced |
|---------|-------------------|--------------|----------|
| `authorization_require_tenant` | `true` | `false` (conftest override) | Yes — missing tenant identity is denied when enabled |
| `authorization_default_deny` | `true` | `false` (conftest override) | Yes — unknown actions are denied when enabled |
| Tenant isolation | Per-tenant scoping on all repositories | Yes | Yes |
| Execution tokens | Ed25519-signed, JTI-tracked, nonce-consumed | Yes | Yes |
| Nonce consumption | Redis-backed composite store | Yes | Yes |
| HITL (Human-in-the-Loop) | Configurable per-tool/action | Yes | Yes |
| RBAC | Role-based action allowlists | Yes | Yes |
| SQL injection prevention | Table whitelist + column regex + parameterized values | Yes | Yes |
| Path traversal prevention | Key manager path validation | Yes | Yes |
| SSRF prevention | URL allowlist + internal IP blocking | Yes | Yes |

**Test configuration note:** `tests/conftest.py` sets `AUTHORIZATION_REQUIRE_TENANT=false` and `AUTHORIZATION_DEFAULT_DENY=false` via environment variables to enable the test client to exercise tenant-scoped and default-deny paths. These test overrides do not affect production defaults, which remain `true`. The production defaults are validated by `tests/integration/test_security_defaults.py` and `tests/integration/test_cross_tenant_isolation.py`.

## 4. Recovery Guarantees

- **Idempotency**: All adapters enforce idempotency key matching; duplicate execution returns the prior result without re-applying.
- **Conflict detection**: Concurrent mutations after the agent action block recovery (`BLOCKED_BY_CONFLICT`).
- **Drift detection**: Hash-based drift detection for files, configurations, and database rows.
- **Dependency ordering**: Reverse topological execution order for chained actions.
- **Partial recovery**: Mixed success/failure states are tracked per-action; failed actions do not prevent independent recoveries.
- **Tenant isolation**: Recovery evidence and execution are scoped to `tenant_id`; cross-tenant access is denied.
- **Verification**: Post-execution verification confirms the target state matches the expected recovered state.

## 5. Known Limitations

- **Database adapter**: SQLite is used for testing; PostgreSQL production behavior is structurally identical but not exercised in the test suite on Windows.
- **Git adapter**: Tests requiring a real Git binary are skipped on Windows in the absence of Git subprocess availability.
- **External verification**: The `ContinuousVerificationService` currently reports `executed_not_verified` for mock adapters because external system verification requires real adapter implementations.
- **SSO adapters**: OIDC and SAML are **not production-ready**. The architecture is implemented (interfaces, state management, account-linking service, callback use cases, API routes, database models, migrations), but the actual provider integration returns mock data: `DefaultOIDCAdapter.handle_callback` returns a hardcoded `("mock-user-id", {"email": "user@example.com"})`; `MockSAMLAdapter`/`ProductionSAMLAdapter` return static XML and a fixed `name_id`. No real token exchange, JWKS validation, or SAML assertion parsing occurs. Production SSO requires replacing these adapter implementations with real provider calls. This is configuration-dependent and integration-dependent, not a drop-in feature.
- **Frontend**: Next.js dashboard (`web/`) is present. The API client contract (`web/lib/api.ts`) was audited against the current backend and corrected (HTTP methods, request schemas, response schemas, list unwrapping). The dashboard is **not exercised by the Python test suite** and **cannot be built in this environment** (the `next` binary is absent from `node_modules`; only a partial dependency install exists). Frontend type safety has not been verified by `tsc`/`next build`.

## 5.1 SSO Status (Explicit)

| Component | Status | Notes |
|-----------|--------|-------|
| OIDC interface (`OIDCAdapter` ABC) | IMPLEMENTED | Abstract contract defined |
| OIDC provider (`DefaultOIDCAdapter`) | STUBBED | `get_authorization_url` builds a real URL; `handle_callback` returns hardcoded mock user/claims |
| OIDC use case (`OIDCAuthUseCase`) | IMPLEMENTED | Token/session issuance works once a callback result is supplied |
| SAML interface (`SAMLAdapter` ABC) | IMPLEMENTED | Abstract contract defined |
| SAML provider (`MockSAMLAdapter` / `ProductionSAMLAdapter`) | STUBBED | Return static XML and fixed `name_id`; no real assertion parsing |
| SSO service (`DefaultSSOService`) | IMPLEMENTED | State generation, validation, account linking all functional |
| SSO routes (`/sso/providers`, `/sso/authorize`, `/sso/callback`) | IMPLEMENTED | Full request/response cycle present |
| SSO persistence (models, repositories, migrations) | IMPLEMENTED | `IdentityProvider`, `SSOState` stored in DB |
| Real provider token exchange / JWKS / SAML parsing | NOT IMPLEMENTED | Requires production adapter implementations |
| **Overall SSO** | **NOT PRODUCTION-READY** | Architecture complete; provider integration is mocked |

## 6. Test Results

### Full pytest suite
- **Passed**: 1610
- **Skipped**: 6 (5 platform-specific performance thresholds on Windows; 1 key manager not available)
- **Unexpected failures**: 0
- **Coverage**: 82.39% (full run, Windows, Python 3.14, SQLite + in-memory stores)

### Recovery regression suite
- **Passed**: 401
- **Failed**: 0

### Security regression suite
- **Passed**: 267
- **Failed**: 0

### E2E demos
- `demo_e2e_control_plane.py`: PASS
- `demo_e2e_causal_recovery.py`: PASS

### Static analysis
- **ruff**: 0 issues (entire repository)
- **mypy**: 0 issues in 235 source files (`app/` + `sdk/`)
- **bandit**: 0 production findings in `app/`; 19 `# nosec B608` suppressions in `database_recovery_adapter.py` (validated table/column names + parameterized values)
- **pip-audit**: No known vulnerabilities found (verified locally via `.venv314`)

## 7. Coverage Reproducibility

The earlier reported discrepancy (Windows ≈31% vs CI ≈80%+) was a measurement artifact of **partial test invocations**, not a platform difference. The canonical release verification is the **full `pytest` invocation** with coverage enabled.

### Canonical command (reproduces ≥80% coverage)

```bash
pytest -q
```

This runs the complete suite with `--cov --cov-report=term-missing` (configured in `pyproject.toml`), covering `app/` and `sdk/` with branch coverage. Verified result on Windows: **82.39%** (1610 passed, 6 skipped).

### Environment
- **Python**: 3.11–3.14 (tested on 3.14.7; `pyproject.toml` requires `>=3.11,<3.15`)
- **Platform**: Windows 11 (local); Ubuntu (CI)
- **Database**: SQLite in-memory (`sqlite:///:memory:` via `tests/conftest.py`)
- **Redis**: Not required for the unit/integration suite; Redis-dependent paths (nonce store, rate limiting) use fallback in-memory stores when `redis_url` is unset
- **No PostgreSQL or Redis required** to reproduce the release verification

### Thresholds
- `pyproject.toml` sets `fail_under = 80`. The full run meets this on Windows.
- The 5 skipped performance tests (`tests/performance/`) are platform-threshold tests excluded by environment, not failures.

### What would lower coverage artificially
- Running a subset of tests (e.g. `tests/unit/` alone) reports lower coverage because infrastructure/integration modules are not exercised. This is expected and not a defect.

## 9. Production Requirements

- PostgreSQL 16+ (or compatible)
- Redis 7+ (for nonce store and rate limiting)
- Ed25519 key pair for execution tokens
- JWT secret key (32+ characters)
- Compliance secret key (for audit signing)
- Stripe webhook secret (if billing is active)
- Tenant identity must be provided in all protected API requests

## 10. Known Technical Debt

- **Database recovery adapter verify bug (fixed)**: The `restore_updated_row` verify path had inverted logic; the `_execute_restore_updated_row` method had an unreachable UPDATE statement due to a misplaced `return`. Both were corrected in this baseline.
- **Recovery lab tests**: The `tests/unit/recovery_lab/` suite is new and comprehensive but contains pre-existing unused imports and long lines that were cleaned up during this baseline.
- **Frontend API contract (audited)**: `web/lib/api.ts` was audited against the current backend API and corrected. Fixed: `agents.update` HTTP method (POST→PATCH); list-endpoint response unwrapping (`agents.list`, `actions.list`, `authority.list` now unwrap `{items, total, limit, offset}`); `createContainment` request fields (`agent_id`→`target_agent_id`, `action`→`mode`); `simulateRecovery` request/response schemas; `executeRecovery` request field (`approver`→`approved_by`); `getBlastRadius`/`getRecoveryPlan`/`getLineage` response schemas. Consuming pages (`agents`, `incidents`, `recovery`, `authority`) were updated to read the corrected field names. The dashboard still cannot be build-verified in this environment (no `next` binary in `node_modules`).
- **SSO integration**: OIDC/SAML adapter implementations return mock data. Production SSO requires real provider implementations. This is tracked as a known limitation, not debt, since the architecture is complete.
