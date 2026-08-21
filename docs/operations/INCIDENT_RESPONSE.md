# IntentLock Incident Response Plan

**Document:** Security incident response procedures for IntentLock V4.
**Status:** Plan document. Response infrastructure (logging, metrics, adapters) is implemented; formal incident response workflows are documented here for the first time.

---

## 1. Security Incident Reporting Procedure

### Detection

Security incidents may be detected through:

1. **Automated monitoring**: Security metrics (`SecurityMetrics`) track authorization denials, HITL events, policy decisions, suspicious tool calls, authentication failures, security exceptions, and execution token replays. The `/metrics/security` endpoint (admin-only) provides a real-time snapshot.
2. **Audit log analysis**: JSONL audit trail at `logs/audit_trail.jsonl` contains timestamped events with correlation IDs. Events include `intent_verification`, `approval_approved`, `approval_rejected`, `rate_limit_exceeded`, `rate_limit_redis_failure`, and `approval_approve_failed`.
3. **SIEM integration**: SIEM adapter interfaces (`SplunkSIEMAdapter`, `QRadarSIEMAdapter`, `SentinelSIEMAdapter`) are implemented but disabled by default (`siem_enabled=False`). When enabled, security events can be forwarded to external SIEM platforms.
4. **Ticketing integration**: Ticketing adapter interfaces (`JiraTicketingAdapter`, `ServiceNowTicketingAdapter`) are implemented but disabled by default (`ticketing_enabled=False`). When enabled, incidents can be tracked in external ticketing systems.
5. **Manual reporting**: Users or administrators may report anomalies observed in the UI or SDK output.

### Reporting

To report a security incident:

1. Identify the correlation ID from the audit log or API response headers.
2. Collect relevant audit records from `logs/audit_trail.jsonl` for the affected time window.
3. Notify the incident response team (see Section 4).
4. Create an incident ticket if ticketing integration is enabled, or use the organization's standard incident management process.

**Implementation Status:** Partial. Detection infrastructure (metrics, audit logging, SIEM/ticketing adapter stubs) exists. No automated alerting or formal reporting workflow is implemented.

---

## 2. Severity Classification

| Severity | Description | Response Time | Examples |
|----------|-------------|---------------|----------|
| **P1 — Critical** | Active exploitation, data breach, or system compromise | Immediate (0-15 min) | Forged execution token accepted, unauthorized cross-tenant data access, production key compromise |
| **P2 — High** | Suspicious activity with high confidence of malicious intent | 1 hour | Repeated policy bypass attempts, coordinated rate limit evasion, suspicious privilege escalation |
| **P3 — Medium** | Potential vulnerability or anomalous behavior requiring investigation | 4 hours | Single policy bypass attempt, unauthorized tool access blocked by policy, misconfigured CORS |
| **P4 — Low** | Informational or minor anomaly with no immediate risk | 24 hours | Failed login attempts, rate limit violations, deprecated configuration usage |

**Implementation Status:** Planned. Severity classification is defined here for the first time. No automated severity assignment or escalation workflow exists.

---

## 3. Incident Response Team Roles

| Role | Responsibility |
|------|----------------|
| **Incident Commander** | Coordinates response, makes escalation decisions, communicates with stakeholders |
| **Security Analyst** | Investigates the incident, analyzes audit logs, identifies scope and impact |
| **Infrastructure Engineer** | Manages containment actions (network restrictions, service restarts, secret rotation) |
| **Application Developer** | Provides code-level context, assesses vulnerability, implements fixes |
| **Compliance Officer** | Manages regulatory reporting requirements, evidence preservation, post-incident review |

For small teams, one individual may assume multiple roles.

**Implementation Status:** Planned. Roles are documented here for the first time. No formal team assignment or escalation matrix exists in the codebase.

---

## 4. Containment Procedures

### Immediate Actions (P1/P2)

1. **Isolate affected systems**: Restrict API ingress using firewall or network policies. Block suspicious IPs identified in audit logs.
2. **Rotate secrets**: Rotate `JWT_SECRET_KEY` and execution signing keys immediately if token forgery or key compromise is suspected. See Section 6 and Section 7.
3. **Disable compromised accounts**: Set `is_active=False` for affected user accounts directly in the database.
4. **Revoke sessions**: Since access tokens are stateless JWTs, session revocation requires rotating the signing secret. All existing tokens will fail validation after secret rotation.
5. **Preserve evidence**: Do not restart services or clear logs until evidence is collected (see Section 9).

### Short-Term Actions (P3)

1. Review affected audit log entries and correlation IDs.
2. Block identified attack patterns in `config/policies.yaml`.
3. Adjust rate limit thresholds if evasion is detected.
4. Review and update CORS origins if misconfiguration is suspected.

### Monitoring Actions

- Monitor `SecurityMetrics` counters for spikes in denials, failures, or replays.
- Watch for `rate_limit_exceeded`, `rate_limit_redis_failure`, `approval_approve_failed`, and `security_exception` events in the audit log.

**Implementation Status:** Partial. Infrastructure for evidence collection (audit logs, metrics) exists. Containment actions (secret rotation, account deactivation) require manual steps.

---

## 5. Key Compromise Response

If the JWT secret key or Ed25519 execution signing key is compromised:

1. **Assess scope**: Determine which keys were compromised and for how long. Check audit logs for tokens issued during the compromise window using correlation IDs and JTIs.
2. **Rotate keys immediately**:
   - Generate a new `JWT_SECRET_KEY` (minimum 32 characters, cryptographically random).
   - For execution keys, generate a new Ed25519 key pair and update `EXECUTION_KEY_PATH` or the key directory.
   - Restart the application to load new keys.
   - Note: Key rotation invalidates all existing tokens. Users must re-authenticate.
3. **Review audit trail**: Search `logs/audit_trail.jsonl` for events during the compromise window. Identify:
   - Users who authenticated during the window
   - Execution tokens issued and consumed
   - Actions authorized during the window
4. **Notify affected parties**: Inform users whose tokens were issued during the compromise window.
5. **Assess regulatory impact**: Determine if the compromise triggers breach notification requirements under applicable regulations (GDPR, SOC 2, etc.).
6. **Post-incident review**: Document the compromise, remediation steps, and preventive measures (see Section 11).

**Key Management Reference:**
- `EnvKeyManager` loads execution keys from `EXECUTION_KEY_PATH` or generates ephemeral keys.
- `VersionedKeyManager` persists and rotates Ed25519 keys in a key directory.
- JWKS endpoint (`/.well-known/jwks.json`) publishes active and previous keys for verification.
- Maximum of 2 previous keys are retained for verification during rotation.

**Implementation Status:** Partial. Key rotation mechanisms exist (versioned keys, JWKS). No automated key compromise detection or emergency rotation workflow exists.

---

## 6. Credential Compromise Response

If user credentials (passwords, access tokens) are compromised:

1. **Identify affected accounts**: Use `get_by_email` or database queries to locate affected user accounts.
2. **Deactivate accounts**: Set `is_active=False` for compromised accounts. This prevents authentication but does not invalidate existing access tokens (which are stateless).
3. **Rotate JWT secret**: Rotate `JWT_SECRET_KEY` to invalidate all existing access tokens. Users must re-authenticate.
4. **Force password reset**: There is no password reset API in V4. Password reset requires direct database modification of the `hashed_password` field. The user must be notified through out-of-band channels to set a new password.
5. **Review audit trail**: Check `logs/audit_trail.jsonl` for actions performed by the compromised account. Correlate using `user_id` and `correlation_id`.
6. **Notify affected users**: Inform users of the compromise and required actions (re-authentication, password change).
7. **Assess scope**: Determine if the compromise affected multiple tenants or if privilege escalation occurred.

**Implementation Status:** Partial. Account deactivation is possible via database modification. No password reset API, no token revocation list, and no automated credential compromise detection exist.

---

## 7. Tenant Security Incident Handling

If a security incident affects a specific tenant:

1. **Isolate the tenant**: If cross-tenant access is enabled (`authorization_require_tenant=True`), verify that the tenant boundary is enforced. If not, enable it immediately.
2. **Review tenant-scoped audit events**: Filter `logs/audit_trail.jsonl` by `tenant_id` to scope the investigation.
3. **Review HITL requests**: Use `HITLQueue.list_pending_requests(tenant_id=...)` to identify pending approvals for the affected tenant.
4. **Review tenant users**: Query `UserRepository.get_by_tenant(tenant_id)` to enumerate tenant users.
5. **Assess data exposure**: Determine if data from other tenants was accessed. Check:
   - Audit log for cross-tenant API calls
   - Policy evaluation logs for resource access patterns
   - Execution token records for tools invoked by the compromised tenant
6. **Notify tenant administrators**: Communicate the incident, scope, and remediation steps to the affected tenant's administrators.
7. **Document tenant-specific evidence**: Preserve audit records, correlation IDs, and execution tokens for the affected tenant's time window.

**Implementation Status:** Partial. Tenant identification in audit records and HITL filtering by tenant exist. No automated tenant isolation verification or tenant-specific incident workflows exist.

---

## 8. Evidence Preservation

### Audit Log Preservation

The primary evidence source is `logs/audit_trail.jsonl`. To preserve evidence:

1. **Do not clear or rotate logs** during an active investigation.
2. **Copy logs immediately**: Create a read-only copy of the audit log file with a timestamped filename (e.g., `audit_trail-2026-08-21-185200.jsonl`).
3. **Verify hash chain integrity**: Use the `_verify_hash_chain()` function or export the audit log via `export_audit_log()` to confirm integrity.
4. **Export compliance evidence**: Use `ExportComplianceEvidenceUseCase` (admin-only endpoint `/compliance/evidence`) to generate a tamper-evident evidence package with HMAC integrity. This requires `compliance_secret_key` to be configured.
5. **Capture metrics snapshot**: Use `/metrics/security` (admin-only) to capture the current security metrics state.

### Evidence to Collect

- Audit log records for the affected time window (filter by `timestamp` and `correlation_id`)
- Security metrics snapshot
- Compliance evidence package (HMAC-signed)
- Execution token records (JTIs, timestamps, agent IDs)
- Approval request records for affected tenants
- Policy evaluation results for affected actions

### Evidence Chain of Custody

- Record the time, date, and individual who collected the evidence.
- Store evidence copies on immutable or write-once storage.
- Document all access to evidence materials.

**Implementation Status:** Partial. Audit logging, hash-chain integrity, compliance evidence export, and security metrics exist. No formal evidence preservation workflow or chain-of-custody tracking is implemented.

---

## 9. Communication Plan

### Internal Communication

| Audience | Information | Channel | Timing |
|----------|-------------|---------|--------|
| Incident Response Team | Full incident details, scope, impact | Direct communication (chat, call) | Immediate (P1/P2) |
| Engineering Leadership | Incident summary, containment status, estimated resolution | Status update | Within 1 hour (P1/P2), 4 hours (P3) |
| Legal/Compliance | Breach assessment, regulatory implications | Formal notification | Within 24 hours if regulatory reporting is triggered |
| All Staff | High-level summary (if public disclosure is required) | Company-wide communication | As determined by legal/compliance |

### External Communication

- **Customers**: Notify affected tenants of data exposure or service impact as required by contract and regulation.
- **Regulators**: Report breaches as required by applicable regulations (GDPR 72-hour window, state breach laws, etc.).
- **Vendors**: Notify SIEM/ticketing providers if their systems were not the source but may contain relevant logs.

### Communication Principles

- Be accurate, not speculative.
- Document all communications with timestamps.
- Do not disclose technical details that could aid further exploitation.
- Designate a single spokesperson for external communications.

**Implementation Status:** Planned. No automated notification or communication workflows exist.

---

## 10. Post-Incident Review Process

After containment and recovery:

1. **Timeline reconstruction**: Use correlation IDs and audit logs to reconstruct the complete incident timeline.
2. **Root cause analysis**: Determine the underlying cause (vulnerability, misconfiguration, process failure).
3. **Impact assessment**: Quantify data exposure, service disruption, and reputational impact.
4. **Remediation verification**: Confirm that containment actions were effective and the vulnerability is closed.
5. **Process improvements**: Identify gaps in detection, response, and prevention.
6. **Documentation update**: Update this incident response plan and related security documentation.
7. **Training**: Conduct team training on the incident and preventive measures.

**Post-Incident Review Timeline:**
- Preliminary review: Within 5 business days
- Final report: Within 15 business days

**Implementation Status:** Planned. No formal post-incident review process or template exists.

---

## 11. Recovery Procedures

### Service Recovery

1. **Verify integrity**: Confirm that all secrets have been rotated, compromised accounts are deactivated, and vulnerabilities are patched.
2. **Restore from backup**: If data corruption or loss occurred, restore PostgreSQL and Redis from tested backups.
3. **Gradual reintroduction**: Re-enable API ingress gradually. Monitor metrics and audit logs for renewed anomalies.
4. **Token validation**: Verify that new tokens are being issued correctly and old tokens are rejected.

### Key Recovery

- If using `EnvKeyManager` with `EXECUTION_KEY_PATH`: Replace the key file and restart the application.
- If using `VersionedKeyManager` with `key_dir`: Place the new key in the key directory. The active key is promoted on rotation.
- Publish the new public key via `/.well-known/jwks.json` for downstream verification.

### Data Recovery

- PostgreSQL: Restore from `pg_dump` or WAL replay. Verify `alembic check` and `alembic current` after restore.
- Redis: Restore from RDB/AOF backup. Verify nonce store and rate limiter functionality.
- Audit logs: Restore `logs/audit_trail.jsonl` from backup and verify hash chain integrity.

### Verification Checklist

- [ ] `GET /api/v1/health` returns 200
- [ ] `GET /api/v1/ready` returns 200 with `db=ok` and `redis=ok` (or `redis=disabled` in dev)
- [ ] New access tokens are issued and validated correctly
- [ ] Execution tokens are issued, consumed, and replay is rejected
- [ ] Audit log is writing new records with valid hash chains
- [ ] Security metrics are collecting data
- [ ] Rate limiting is functioning (Redis-backed in production, in-memory in dev)
- [ ] HITL queue is operational

**Implementation Status:** Partial. Service health endpoints, key management, and backup/restore procedures are documented in architecture. No formal recovery runbook or automated recovery procedures exist.

---

## 12. Incident Response Infrastructure Status

| Component | Status | Description |
|-----------|--------|-------------|
| Audit logging | Implemented | JSONL structured events with correlation IDs and hash-chain integrity |
| Security metrics | Implemented | In-memory counters for denials, HITL, policy, auth, execution tokens |
| Metrics endpoint | Implemented | `/metrics/security` (admin-only) |
| SIEM integration | Partial | Adapter stubs (Splunk, QRadar, Sentinel); disabled by default |
| Ticketing integration | Partial | Adapter stubs (Jira, ServiceNow); disabled by default |
| Monitoring integration | Partial | Adapter stub; disabled by default |
| Automated alerting | Planned | No automated alerting on security events |
| Evidence export | Implemented | HMAC-signed compliance evidence package (requires `compliance_secret_key`) |
| Key rotation | Implemented | Versioned Ed25519 keys with grace period; manual process |
| Account deactivation | Partial | Requires direct database modification; no API |
| Password reset | Planned | No API exists |
| Token revocation | Planned | No server-side revocation list; requires secret rotation |

---

## 13. Related Documentation

- [`docs/architecture/ARCHITECTURE.md`](docs/architecture/ARCHITECTURE.md) — Trust boundaries, key management, operational checklist
- [`docs/security/AUTHZ_ARCHITECTURE.md`](docs/security/AUTHZ_ARCHITECTURE.md) — Authorization architecture, RBAC, session security
- [`docs/security/TENANT_ISOLATION.md`](docs/security/TENANT_ISOLATION.md) — Multi-tenant data model and isolation enforcement
- [`docs/security/SECURITY_ASSURANCE_REPORT.md`](docs/security/SECURITY_ASSURANCE_REPORT.md) — Security controls, test evidence, findings
