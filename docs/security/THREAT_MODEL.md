# Interlock V4 Threat Model

**Date:** 2026-08-21  
**Repository:** `F:\Desktop_Data_2026\Desktop\INTERLOCK V4`  
**Version:** V4  
**Status:** Approved — Suitable for production with documented residual risks

---

## 1. Assets

| Asset | Sensitivity | Description |
|-------|-------------|-------------|
| User accounts | High | Tenant/user identities persisted in PostgreSQL; subject to authentication and authorization |
| Access tokens (JWT HS256) | High | Bearer tokens for `/auth/*` and `/approval/*`; grant user-level access |
| Execution tokens (JWT Ed25519) | High | Time-limited, single-use tokens authorizing protected tool invocations |
| JWT signing keys (HS256) | Critical | Secret key material for access token signing; exposure enables token forgery |
| Execution signing keys (Ed25519) | Critical | Private key material for execution token signing; exposure enables token forgery |
| Nonce store (Redis) | High | Atomic replay-protection state; corruption enables replay attacks |
| Audit records | High | JSONL logs with hash-chain tamper evidence; used for forensics and compliance |
| Approval decisions | High | HITL (Human-in-the-Loop) authorization state; tampering enables unauthorized actions |
| Policies (YAML) | High | Blocked patterns and risk scoring rules; bypass enables malicious tool use |
| Tenant data | High | Isolation-bound user data and execution contexts |
| Secrets / configuration | Critical | `JWT_SECRET_KEY`, `EXECUTION_KEY_PATH`, database credentials, Redis passwords |
| Compliance evidence packages | Medium | HMAC-signed exports; integrity depends on `compliance_secret_key` |

---

## 2. Threat Actors

| Actor | Motivation | Capability |
|-------|-----------|------------|
| External attackers | Financial gain, disruption, data theft | Moderate — can probe endpoints, inject payloads, attempt credential theft |
| Malicious tenants | Bypass policy, access other tenants' data | Moderate — has valid credentials, understands policy structure |
| Compromised users | Lateral movement, unauthorized tool invocation | High — holds valid credentials, may access audit history |
| Compromised AI agents | Forge execution tokens, invoke protected tools without approval | Moderate — depends on stolen or misconfigured agent credentials |
| Insider threats | Data exfiltration, policy manipulation | High — internal network access, may have deployment credentials |
| Supply-chain attackers | Backdoor dependencies, CI/CD compromise | High — can inject malicious code into build or dependency chain |

---

## 3. Trust Boundaries

| Boundary | Enforcement | Description |
|----------|-------------|-------------|
| Agent/Tool → Gateway | JWT access token (`CurrentUser`), network ACLs | Agents must authenticate with bearer tokens to call `/intent/verify` and `/intent/execute` |
| User → Gateway | JWT access token (`type=access`) | `/auth/me` and `/approval/*` routes enforce bearer authentication |
| Gateway → Redis | Redis AUTH (`--requirepass`), fail-closed behavior | Atomic nonce consumption and distributed rate limiting; Redis failure denies execution in production |
| Gateway → Database | SQLAlchemy ORM, connection pooling, PostgreSQL credentials | Durable persistence of users, approvals, audit events, execution token records |
| Gateway → External (LLM/Tools) | SDK enforces single-use semantics before tool invocation | SDK validates gateway response, then invokes wrapped local tool; gateway does not directly execute business logic |

**Note on deployment topology:** The architecture assumes TLS termination at an upstream load balancer. The Interlock V4 gateway itself does not serve TLS in the example Docker Compose configuration. Network segmentation, firewall rules, and service mesh policies are deployment responsibilities.

---

## 4. Threat Analysis (STRIDE)

### 4.1 Spoofing

#### S1: Forged Access Token (HS256)
- **Threat description:** An attacker forges a valid access token to impersonate a user or tenant.
- **Attack scenario:** Attacker obtains or guesses the `JWT_SECRET_KEY`, creates a JWT with `type=access`, arbitrary `sub`, and valid `iat`/`exp`/`nbf`/`jti`.
- **Risk:** Critical
- **Impact:** Full authentication bypass; attacker can submit intents, approve their own requests, and access audit data.
- **Mitigation:** HS256 signing with high-entropy `JWT_SECRET_KEY`; strict claim validation (`type=access`, `sub`, `iat`, `nbf`, `exp`, `jti`); clock skew tolerance.
- **Remaining risk:** Key material compromise is catastrophic and undetectable without external HSM/KMS integration.

#### S2: Forged Execution Token (Ed25519)
- **Threat description:** An attacker forges a valid execution token to bypass approval workflow.
- **Attack scenario:** Attacker obtains the Ed25519 private key, creates a signed token with valid claims, or replays a previously valid token.
- **Risk:** Critical
- **Impact:** Policy bypass; attacker can invoke protected tools without approval.
- **Mitigation:** Ed25519 signing; atomic nonce consumption in Redis; strict expiry check; versioned key manager with key IDs (`kid`) and grace periods.
- **Remaining risk:** Private key compromise enables complete execution token forgery. No automated key rotation.

#### S3: Stolen Replay of Valid Token
- **Threat description:** An attacker intercepts or steals a valid access or execution token and replays it.
- **Attack scenario:** Attacker captures a JWT from logs, network traffic, or browser storage and replays it within its validity window.
- **Risk:** High
- **Impact:** Unauthorized access or tool invocation.
- **Mitigation:**
  - Access tokens: short expiration, bearer semantics (stateless).
  - Execution tokens: atomic nonce consumption (`SET NX EX`) in Redis; fail-closed on Redis failure in production.
- **Remaining risk:** Access tokens have no server-side replay protection. Execution tokens have single-use guarantees only if Redis is available.

---

### 4.2 Tampering

#### T1: Audit Log Tampering
- **Threat description:** An attacker with file system access modifies JSONL audit records to hide malicious activity.
- **Attack scenario:** Insider or compromised host edits audit log lines to alter `jti`, timestamps, or approval decisions.
- **Risk:** High
- **Impact:** Loss of forensic integrity; compliance violations; inability to reconstruct incident.
- **Mitigation:** Hash-chain tamper evidence in JSONL audit logs; each record references the previous record's hash.
- **Remaining risk:** Hash chain detects modification but does not prevent it. If attacker has persistent host access, they can modify both records and chain links.

#### T2: Policy Configuration Tampering
- **Threat description:** An attacker modifies `config/policies.yaml` to bypass security checks.
- **Attack scenario:** Compromised CI/CD pipeline or insider alters blocked patterns, transfer limits, or payload rules.
- **Risk:** High
- **Impact:** Malicious tool use (SQL injection, shell commands, exfiltration) goes undetected.
- **Mitigation:** Policy engine uses compiled regex patterns with word boundaries; deterministic risk scoring.
- **Remaining risk:** Runtime policy changes are not integrity-protected. Compromise before deployment propagates to production.

#### T3: Redis Nonce Store Manipulation
- **Threat description:** An attacker with Redis access deletes or inserts nonces to enable replay attacks.
- **Attack scenario:** Attacker connects to Redis (without or with credentials) and sets arbitrary `jti` values.
- **Risk:** High
- **Impact:** Replay attacks bypass atomic nonce consumption; attackers can reuse execution tokens.
- **Mitigation:** Redis AUTH (`--requirepass`); fail-closed behavior denies execution when Redis is unavailable in production.
- **Remaining risk:** Redis authentication was previously absent and was remediated. Credential strength and rotation are deployment responsibilities.

#### T4: Approval Decision Tampering
- **Threat description:** An attacker modifies approval requests or decisions in PostgreSQL.
- **Attack scenario:** SQL injection (unlikely due to ORM), compromised database credentials, or direct DB access alters approval state.
- **Risk:** High
- **Impact:** Unauthorized tool execution through tampered HITL decisions.
- **Mitigation:** SQLAlchemy ORM with parameterized queries; HITL requests durably persisted; role-based approver authorization.
- **Remaining risk:** Database credential compromise is catastrophic. No database-level access control (e.g., row-level security) is implemented.

---

### 4.3 Repudiation

#### R1: Denied Authorization Actions
- **Threat description:** A malicious user denies performing unauthorized tool invocations or approvals.
- **Attack scenario:** Attacker claims their credentials were stolen or they did not approve a specific action.
- **Risk:** Medium
- **Impact:** Accountability gap; difficult to reconstruct incidents.
- **Mitigation:** Audit logging with correlation IDs, `jti` tracking, hash-chain integrity, and `sub`/tenant attribution.
- **Remaining risk:** Audit logs are not externally signed or shipped to a SIEM in the core product. Compliance evidence export provides HMAC integrity but requires manual invocation.

---

### 4.4 Information Disclosure

#### ID1: Sensitive Data in Audit Logs
- **Threat description:** Tool arguments or execution tokens are inadvertently logged, exposing secrets.
- **Attack scenario:** Attacker with log access reads plaintext secrets, passwords, or PII from JSONL files.
- **Risk:** Medium
- **Impact:** Secret exposure; compliance violation (GDPR, SOC 2).
- **Mitigation:** Audit logger explicitly excludes tool arguments and execution tokens from records; logs contain correlation IDs, `sub`, tool names, and policy decisions only.
- **Remaining risk:** Future code changes may inadvertently log sensitive fields. Log review is required at release.

#### ID2: JWKS Key Material Exposure
- **Threat description:** The JWKS endpoint exposes public verification keys that assist attackers.
- **Attack scenario:** Attacker scrapes JWKS to understand key versions and rotation cadence.
- **Risk:** Low
- **Impact:** Reconnaissance; enables targeted key-compromise or DoS attacks.
- **Mitigation:** JWKS exposes only public keys (Ed25519 public components). Private keys never leave the server.
- **Remaining risk:** Public key material is intended to be public. Exposure is not a secret compromise.

#### ID3: Tenant Data Leakage
- **Threat description:** Authorization context does not enforce tenant isolation, allowing cross-tenant data access.
- **Attack scenario:** Malicious tenant queries or approves resources belonging to another tenant.
- **Risk:** High
- **Impact:** Data breach; confidentiality loss; compliance violation.
- **Mitigation:** Authorization context includes `tenant_id`; configurable tenant requirement enforcement; database models scoped by tenant.
- **Remaining risk:** Tenant isolation relies on application-layer checks. A bug in tenant-scoping could leak data. No row-level security (RLS) at the database layer.

#### ID4: Secret Exposure in Environment Variables
- **Threat description:** Secrets are passed via environment variables and exposed in process listings or logs.
- **Attack scenario:** Insider or compromised host inspects `/proc/<pid>/environ` or container environment for credentials.
- **Risk:** Medium
- **Impact:** Credential theft enabling token forgery or database/Redis compromise.
- **Mitigation:** Deployment-managed secrets (Vault, AWS Secrets Manager, Docker Secrets) recommended; Dockerfile build-time secret exposure check.
- **Remaining risk:** Environment variables are not encrypted at rest in memory. Production deployments must use secrets management.

---

### 4.5 Denial of Service

#### D1: Execution Token Exhaustion (Nonce Store DoS)
- **Threat description:** An attacker floods the `/intent/execute` endpoint to consume valid nonces or exhaust Redis memory.
- **Attack scenario:** Attacker sends thousands of valid execution tokens (obtained via legitimate intent verification) to consume Redis nonces.
- **Risk:** Medium
- **Impact:** Legitimate execution tokens rejected; execution pipeline halts.
- **Mitigation:** Rate limiting (in-memory + Redis distributed); request size limits (default 1 MiB); fail-closed Redis behavior.
- **Remaining risk:** Rate limiting is process-local when Redis is unavailable. A distributed attacker could bypass per-instance limits.

#### D2: Large Request Body DoS
- **Threat description:** An attacker sends extremely large request bodies to exhaust memory or disk.
- **Attack scenario:** Attacker POSTs multi-GB payloads to `/intent/verify` or `/intent/execute`.
- **Risk:** Medium
- **Impact:** Memory exhaustion; service degradation or crash.
- **Mitigation:** `RequestSizeLimitMiddleware` enforces configurable `request_max_body_bytes` (default 1 MiB).
- **Remaining risk:** Very low. Configurable limit can be tuned per deployment.

#### D3: Policy Engine DoS via Regex
- **Threat description:** Attacker crafts payloads that cause catastrophic backtracking in regex patterns.
- **Attack scenario:** Malicious input triggers exponential-time regex evaluation in the policy engine.
- **Risk:** Medium
- **Impact:** CPU exhaustion; service unavailability.
- **Mitigation:** Policy patterns use bounded regex with word boundaries; input normalization before matching.
- **Remaining risk:** Regex complexity is bounded by pattern authors. Malicious or buggy YAML policies could introduce ReDoS.

#### D4: Redis DoS
- **Threat description:** Attacker causes Redis to become unavailable, preventing execution token consumption and rate limiting.
- **Attack scenario:** Network partition, memory exhaustion, or authentication flood against Redis.
- **Risk:** Medium
- **Impact:** Execution tokens cannot be consumed (fail-closed); rate limiting degrades to per-instance.
- **Mitigation:** Redis health checks; fail-closed on Redis failure in production; persistent volumes.
- **Remaining risk:** Redis is a single point of failure for execution token replay protection.

---

### 4.6 Elevation of Privilege

#### E1: Role Escalation in HITL
- **Threat description:** A non-approver user escalates privileges to approve their own HITL requests.
- **Attack scenario:** Attacker modifies their role claim or bypasses `hitl_approver_roles` validation.
- **Risk:** High
- **Impact:** Unauthorized approval of blocked or high-risk tool invocations.
- **Mitigation:** Role-based approver check via `hitl_approver_roles` setting; JWT `type=access` validation.
- **Remaining risk:** Role-based checks rely on application-layer JWT claims. If an attacker can forge an access token with elevated roles, they bypass the check.

#### E2: Tenant Boundary Escape
- **Threat description:** Attacker escapes tenant isolation to access other tenants' data or approvals.
- **Attack scenario:** Attacker crafts requests with another tenant's `tenant_id` or manipulates authorization context.
- **Risk:** High
- **Impact:** Cross-tenant data breach; policy bypass.
- **Mitigation:** `tenant_id` bound to authenticated user context; configurable tenant requirement.
- **Remaining risk:** Application-layer tenant scoping. No database RLS.

---

### 4.7 Webhook / External Attacks

#### W1: Webhook Spoofing / Replay
- **Threat description:** An attacker intercepts or spoofs webhook callbacks from the Interlock V4 gateway to downstream services.
- **Attack scenario:** Attacker sends forged webhook payloads to approval or integration endpoints.
- **Risk:** Medium
- **Impact:** Fraudulent approval decisions; false audit events.
- **Mitigation:** Integration adapters (IAM, monitoring, SIEM, ticketing) implement health checks and factory routing. Webhook signatures are deployment-specific and not in the core product.
- **Remaining risk:** No built-in webhook signature validation or replay protection for outbound webhooks. This is an implementation gap for future deployment-specific adapters.

---

### 4.8 Dependency / Supply Chain

#### SC1: Compromised Python Dependencies
- **Threat description:** Attacker compromises a dependency package to inject malicious code.
- **Attack scenario:** Malicious package on PyPI mimics `cryptography` or `fastapi`, or a transitive dependency is compromised.
- **Risk:** High
- **Impact:** Remote code execution; credential theft; data exfiltration.
- **Mitigation:** pip-audit, Bandit, Semgrep, Safety in CI/CD; CycloneDX SBOM generation; dependency lock files (`requirements.txt`).
- **Remaining risk:** Lock files pin versions but do not guarantee integrity. Supply-chain attacks (e.g., PyPI typosquatting) remain a systemic risk.

#### SC2: Compromised CI/CD Pipeline
- **Threat description:** Attacker compromises the GitHub Actions workflow or build environment.
- **Attack scenario:** Malicious PR modifies CI workflow to exfiltrate secrets or inject backdoors.
- **Risk:** High
- **Impact:** Malicious artifact deployment; secret exposure.
- **Mitigation:** Security scanning workflows; secret scanning in CI; Docker verification workflow.
- **Remaining risk:** No attested build provenance (e.g., SLSA, Sigstore) in CI/CD. Workflow permissions and branch protection rules are deployment responsibilities.

---

### 4.9 Agent Abuse

#### A1: Malicious Agent Invoking Blocked Tools
- **Threat description:** A compromised or rogue AI agent submits intents for blocked or high-risk tools.
- **Attack scenario:** Agent's access token is stolen; attacker submits `DROP TABLE` or shell command as a tool invocation.
- **Risk:** High
- **Impact:** Data destruction; unauthorized system access.
- **Mitigation:** Policy engine with regex blocked patterns and `sqlglot` destructive-SQL detection; shell metacharacter detection; SSRF and path traversal protection.
- **Remaining risk:** Policy bypass via novel payloads (e.g., encoding, casing, newline injection) is a continuous risk. The policy engine must be updated as attack techniques evolve.

#### A2: Agent Impersonation
- **Threat description:** Attacker impersonates a legitimate agent by stealing its credentials or JWT.
- **Attack scenario:** Attacker extracts `JWT_SECRET_KEY` or an agent's access token and issues requests as that agent.
- **Risk:** High
- **Impact:** Unauthorized tool invocations attributed to a legitimate agent.
- **Mitigation:** Short-lived access tokens; network-level controls (firewall, service mesh) restricting `/intent/*` access to authorized agent CIDRs.
- **Remaining risk:** JWT access tokens have no server-side revocation or IP binding.

---

## 5. Mitigation Summary

| # | Mitigation | Status | Notes |
|---|-----------|--------|-------|
| 1 | HS256 access token signing with strict claim validation | Implemented | Requires high-entropy `JWT_SECRET_KEY` |
| 2 | Ed25519 execution token signing with `kid` and key versioning | Implemented | Grace period for previous keys |
| 3 | Atomic nonce consumption in Redis (SET NX EX) | Implemented | Fail-closed on Redis failure in production |
| 4 | JWT claim validation (iat, nbf, exp, jti, type) | Implemented | Clock skew tolerance configured |
| 5 | Policy engine with regex blocked patterns and word boundaries | Implemented | YAML-configured; continuous review required |
| 6 | Destructive SQL detection via sqlglot parser | Implemented | Covers DDL and dangerous DML |
| 7 | Shell injection metacharacter detection | Implemented | Argument-level filtering |
| 8 | Path traversal rejection (`..` component check) | Implemented | Applies to key directories and tool arguments |
| 9 | SSRF protection (URL scheme, private IP, DNS) | Implemented | Blocks loopback, reserved, and private ranges |
| 10 | Bcrypt password hashing (configurable rounds) | Implemented | 10-15 rounds |
| 11 | CORS with configurable origins | Implemented | `allow_credentials=True` requires careful origin configuration |
| 12 | Security headers (CSP, X-Frame-Options, etc.) | Implemented | Baseline set applied |
| 13 | Correlation IDs per request | Implemented | Propagated in responses and audit logs |
| 14 | JSONL audit logging with hash-chain integrity | Implemented | Excludes tool arguments and execution tokens |
| 15 | HITL approval queue with role-based authorization | Implemented | PostgreSQL-backed durability |
| 16 | Rate limiting (in-memory + Redis distributed) | Implemented | Proxy-aware IP extraction |
| 17 | Request size limits (default 1 MiB) | Implemented | Configurable |
| 18 | Docker image hardening (non-root, tmpfs, labels) | Implemented | Docker verification pending on CI runner |
| 19 | CI/CD security scanning (pip-audit, Bandit, Semgrep, Safety) | Implemented | SBOM generation included |
| 20 | Dependency lock files (pip-tools) | Implemented | Committed to repository |
| 21 | Redis AUTH (`--requirepass`) | Implemented | Parameterized via `REDIS_PASSWORD` |
| 22 | Key rotation (versioned Ed25519 keys) | Implemented | Manual rotation; max 2 previous keys retained |
| 23 | Tenant isolation (`tenant_id` in authorization context) | Implemented | Application-layer only |
| 24 | Compliance evidence export with HMAC integrity | Implemented | Requires configured `compliance_secret_key` |
| 25 | KMS/HSM integration | Partial | `KMSKeyManager` and `HSMKeyProvider` are defined but not integrated with an active provider |
| 26 | Automatic key rotation | Planned | Manual rotation only in V4 |
| 27 | Distributed rate limiting fallback when Redis is down | Partial | Fail-closed in production; rate limiting degrades to per-instance |
| 28 | Webhook signature validation | Planned | Not implemented in core product |
| 29 | Build provenance (SLSA / Sigstore) | Planned | Not implemented in CI/CD |
| 30 | Database row-level security (RLS) | Planned | Not implemented |

---

## 6. Residual Risk Acceptance

| Residual Risk | Rationale | Acceptance Owner |
|---------------|-----------|------------------|
| **Stateless access tokens without server-side replay protection** | Access tokens are short-lived (default expiration) and used only for API authentication. Execution tokens carry the single-use, high-value authorization. Implementing access-token replay protection would require a stateful nonce store for every API request, increasing Redis dependency and latency. The current design accepts this risk in exchange for simplicity and performance. | Architecture / Product |
| **No KMS/HSM integration** | `KMSKeyManager` and `HSMKeyProvider` are extension points. Integrating with external HSM/KMS (AWS KMS, HashiCorp Vault, YubiHSM) requires deployment-specific configuration, networking, and cost. V4 provides the abstraction; production deployments must configure the active provider. | Operations / Security |
| **Process-local rate limiting when Redis is unavailable** | Redis failure in production triggers fail-closed behavior for execution token consumption. Rate limiting falls back to in-memory counters, which are per-instance. This is an intentional trade-off: availability of execution authorization is preserved at the cost of global rate enforcement during Redis outages. | Operations / SRE |
| **CORS with `allow_credentials=True`** | Credential-enabled CORS is required for browser-based approval UIs. Misconfiguration of `CORS_ORIGINS` could enable credential theft. The risk is accepted because CORS is a browser-side enforcement mechanism and the primary trust boundary is bearer-token authentication. Production deployments must restrict `CORS_ORIGINS` to trusted domains. | Frontend / DevOps |
| **Application-layer tenant isolation (no database RLS)** | Tenant isolation is enforced in the application layer via `tenant_id` in the authorization context. Database-level row-level security (RLS) is not implemented. The risk is accepted because the application is the sole data access path (no direct database access from tenants). Future deployments requiring stronger isolation should enable PostgreSQL RLS. | Database / Security |
| **No automated key rotation** | Key rotation is manual. Automatic rotation introduces complexity around grace periods, JWKS consistency, and token invalidation windows. Manual rotation with documented procedures is accepted for V4, with automated rotation planned for a future release. | Operations / Security |
| **Docker build/runtime not verified on review machine** | Docker verification requires Docker Engine, which was unavailable during this review. A GitHub Actions workflow (`.github/workflows/docker-verify.yml`) has been added to perform these checks on CI runners. The risk is accepted because the Dockerfile and Compose file have been manually reviewed for security hardening, and CI verification is in place. | DevOps / CI |
| **No independent professional security assessment** | This review is AI-assisted and does not constitute formal penetration testing or code audit by an independent security firm. The risk is accepted for proof-of-intent and pilot deployments. High-assurance deployments (banking, healthcare, government) must obtain independent evaluation before production. | Legal / Compliance |
| **Execution token TTL minimum of 1 second** | Very short execution token TTLs may cause race conditions in high-latency environments. A 1-second minimum is enforced to prevent clock-skew-related denials. The residual risk of clock desynchronization is accepted; NTP synchronization is a deployment prerequisite. | Infrastructure |

---

## 7. Compliance and Regulatory Considerations

| Regulation | Relevance | Controls |
|-----------|-----------|----------|
| SOC 2 | Audit logging, access control, change management | JSONL audit logs with hash-chain integrity; JWT authentication; role-based HITL; CI/CD change management |
| GDPR | Data minimization, audit trails, access control | Audit logs exclude sensitive payloads; tenant isolation; right-to-erasure requires PostgreSQL record deletion procedures |
| PCI-DSS | If used in payment flows | Network segmentation (deployment responsibility); strong cryptography (Ed25519, HS256); access control; audit trails |
| HIPAA | If used in healthcare workflows | Access control; audit logging; encryption at rest (deployment responsibility for PostgreSQL disk encryption); integrity controls (hash-chain) |

**Note:** Interlock V4 is a control plane, not a data store. It does not store PII, PHI, or payment data by design. Compliance posture depends on deployment configuration, database encryption, and log retention policies.

---

## 8. Review and Update History

| Date | Reviewer | Changes |
|------|----------|---------|
| 2026-08-21 | Kilo (AI-assisted) | Initial threat model document created |
| 2026-08-16 | Kilo (AI-assisted) | Security Assurance Report completed; 8 findings remediated |
| 2026-08-16 | Kilo (AI-assisted) | Architecture documentation updated with trust boundaries and failure behavior |

---

*This document is part of the Interlock V4 security documentation set. Review quarterly or after significant architectural changes.*
