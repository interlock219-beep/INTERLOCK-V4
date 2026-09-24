# Interlock V4 — 1000+ Capability Master Roadmap

## Purpose
This roadmap lists every candidate capability for the Interlock V4 evolution program. Each capability has a unique ID, domain, description, value, dependencies, implementation status, test requirement, risk level, performance impact, compatibility impact, and documentation requirement.

## Prioritizing
- **P0** — safety/security/correctness-critical
- **P1** — core product differentiation (control, containment, recovery, verification)
- **P2** — major enterprise/customer value
- **P3** — meaningful ecosystem/developer-experience improvements
- **P4** — optional enhancements

## Status Legend
- `PLANNED` — capability identified, no implementation started
- `IN_PROGRESS` — active implementation
- `IMPLEMENTED` — code written, tests passing, doc updated
- `PARTIAL` — implementation partially complete
- `DEFERRED` — implementation blocked or not valuable now

## Implementation Waves
Wave 1: Architecture hardening, immutable evidence, universal state capture (Phase 0 completion)
Wave 2: P0 correctness/security gaps (tokens, policy, identity)
Wave 3: Containment expansion (network, tool isolation)
Wave 4: Recovery coverage (cloud, K8s, SaaS adapters)
Wave 5: Verification hardening (hash verification, schema, invariants)
Wave 6: Forensics (Merkle trees, evidence chain)
Wave 7: Universal action model
Wave 8: Resource/dependency graph
Wave 9: Simulation and digital twin
Wave 10: Chaos and resilience
Wave 11: MCP/A2A security
Wave 12: Agent framework integrations
Wave 13: Cloud/infrastructure adapters
Wave 14: Enterprise security
Wave 15: Observability (OpenTelemetry)
Wave 16: Developer experience and CLI
Wave 17: Scale and performance
Wave 18: Security research tooling
Wave 19: AI-assisted security/recovery
Wave 20: Final hardening

---

# DOMAIN 01 — IDENTITY & AGENT IDENTITY

| ID | Capability | Priority | Status |
|---|---|---|---|
| IDY-001 | Cryptographic agent identity with Ed25519 | P0 | IMPLEMENTED |
| IDY-002 | Session-bound agent identity | P0 | IMPLEMENTED |
| IDY-003 | Workload identity binding to service account | P1 | PLANNED |
| IDY-004 | Identity inheritance from parent agent to sub-agent | P1 | PARTIAL |
| IDY-005 | Delegated identity with chain validation | P0 | IMPLEMENTED |
| IDY-006 | Identity expiration with automatic revocation | P1 | PLANNED |
| IDY-007 | Identity rotation without service interruption | P1 | PLANNED |
| IDY-008 | Identity provenance chain from root human to agent | P1 | PARTIAL |
| IDY-009 | Identity confidence scoring based on trust signals | P1 | PLANNED |
| IDY-010 | Identity anomaly detection (impossible travel, impossible delegation) | P0 | PLANNED |
| IDY-011 | Identity impersonation detection via behavioral biometrics | P1 | PLANNED |
| IDY-012 | Identity revocation with cascade to all derived grants | P0 | PARTIAL |
| IDY-013 | Identity quarantine with evidence preservation | P0 | IMPLEMENTED |
| IDY-014 | Identity lineage graph traversal | P1 | PARTIAL |
| IDY-015 | Cross-system identity mapping (agent_id to external system ID) | P2 | PLANNED |
| IDY-016 | Identity federation via OIDC/SAML (production adapters) | P1 | PARTIAL |
| IDY-017 | Human-to-agent attribution with m-of-n approval | P1 | PARTIAL |
| IDY-018 | Agent-to-agent attribution with full delegation chain | P1 | PARTIAL |
| IDY-019 | Sub-agent identity scoped to parent authority | P1 | PARTIAL |
| IDY-020 | Tool identity registry with trust scores | P1 | PLANNED |
| IDY-021 | Execution environment identity (container, VM, process) | P1 | PLANNED |
| IDY-022 | Ephemeral agent identity for one-shot tasks | P2 | PLANNED |
| IDY-023 | Agent identity backup and restore | P2 | PLANNED |
| IDY-024 | Agent identity compromise indicator | P0 | PLANNED |
| IDY-025 | Agent identity federation across tenants (audit-only) | P2 | PLANNED |

# DOMAIN 02 — AUTHORIZATION

| ID | Capability | Priority | Status |
|---|---|---|---|
| AUTH-001 | Agent-scoped authorization | P0 | IMPLEMENTED |
| AUTH-002 | Session-scoped authorization | P1 | PARTIAL |
| AUTH-003 | Task-scoped authorization | P1 | PLANNED |
| AUTH-004 | Intent-scoped authorization | P0 | IMPLEMENTED |
| AUTH-005 | Tool-scoped authorization | P0 | IMPLEMENTED |
| AUTH-006 | Resource-scoped authorization | P0 | PARTIAL |
| AUTH-007 | Action-scoped authorization | P0 | IMPLEMENTED |
| AUTH-008 | Parameter-scoped authorization | P1 | PLANNED |
| AUTH-009 | Environment-scoped authorization | P1 | PLANNED |
| AUTH-010 | Tenant-scoped authorization | P0 | IMPLEMENTED |
| AUTH-011 | Time-based authorization (time-of-day, day-of-week) | P1 | PLANNED |
| AUTH-012 | Geography-based authorization (legally/operationally appropriate) | P2 | PLANNED |
| AUTH-013 | Data-classification-aware authorization | P1 | PLANNED |
| AUTH-014 | Risk-score-aware authorization | P0 | IMPLEMENTED |
| AUTH-015 | Previous-behavior-aware authorization | P1 | PARTIAL |
| AUTH-016 | Approval-state-aware authorization | P0 | IMPLEMENTED |
| AUTH-017 | Dependency-state-aware authorization | P1 | PLANNED |
| AUTH-018 | Incident-state-aware authorization | P1 | PLANNED |
| AUTH-019 | Recovery-state-aware authorization | P1 | PLANNED |
| AUTH-020 | Policy simulation before deployment | P1 | PLANNED |
| AUTH-021 | Policy explanation with natural language | P1 | PARTIAL |
| AUTH-022 | Policy versioning with rollback | P1 | PARTIAL |
| AUTH-023 | Policy diff across versions | P1 | PLANNED |
| AUTH-024 | Policy testing framework | P1 | PLANNED |
| AUTH-025 | Policy linting | P1 | PLANNED |
| AUTH-026 | Policy conflict analysis | P1 | PLANNED |
| AUTH-027 | Policy inheritance hierarchy | P1 | PLANNED |
| AUTH-028 | Policy delegation | P1 | PLANNED |
| AUTH-029 | Policy expiration | P1 | PLANNED |
| AUTH-030 | Emergency deny all for tenant | P0 | PARTIAL |
| AUTH-031 | Emergency allow with explicit controls | P1 | PLANNED |
| AUTH-032 | Conditional authority with runtime evaluator | P1 | PARTIAL |
| AUTH-033 | Step-up approval for sensitive actions | P1 | PARTIAL |
| AUTH-034 | Just-in-time privilege with automatic expiration | P1 | PLANNED |
| AUTH-035 | One-shot authority with automatic revocation | P0 | IMPLEMENTED |
| AUTH-036 | Authority chaining with depth limits | P0 | IMPLEMENTED |
| AUTH-037 | Authority attenuation enforcement | P1 | PARTIAL |
| AUTH-038 | Authority lineage visualization | P1 | PARTIAL |
| AUTH-039 | Authority replay detection | P1 | PARTIAL |
| AUTH-040 | Authority grant freezing | P1 | PLANNED |
| AUTH-041 | Authority grant suspension | P1 | PLANNED |
| AUTH-042 | Authority grant audit trail | P0 | IMPLEMENTED |
| AUTH-043 | Cross-tenant authority denial | P0 | IMPLEMENTED |
| AUTH-044 | Least-authority enforcement at token issuance | P0 | IMPLEMENTED |
| AUTH-045 | Short-lived execution authority (TTL enforcement) | P0 | IMPLEMENTED |
| AUTH-046 | Tenant isolation enforcement in authorization | P0 | IMPLEMENTED |
| AUTH-047 | Default-deny for unknown actions | P0 | IMPLEMENTED |
| AUTH-048 | Authorization cache with invalidation | P2 | PLANNED |
| AUTH-049 | Authorization decision audit log | P0 | IMPLEMENTED |
| AUTH-050 | Authorization decision replay for forensics | P1 | PLANNED |

# DOMAIN 03 — EXECUTION TOKENS

| ID | Capability | Priority | Status |
|---|---|---|---|
| TOK-001 | Ed25519-signed execution tokens | P0 | IMPLEMENTED |
| TOK-002 | Token expiration enforcement | P0 | IMPLEMENTED |
| TOK-003 | JTI nonce with atomic Redis consumption | P0 | IMPLEMENTED |
| TOK-004 | Audience restriction (aud claim) | P1 | PLANNED |
| TOK-005 | Action restriction in token claims | P0 | IMPLEMENTED |
| TOK-006 | Resource restriction in token claims | P1 | PARTIAL |
| TOK-007 | Parameter binding/hash in token | P1 | PLANNED |
| TOK-008 | Session restriction in token claims | P1 | PARTIAL |
| TOK-009 | Tenant restriction in token claims | P1 | PARTIAL |
| TOK-010 | Context binding (correlation_id, environment) | P1 | PLANNED |
| TOK-011 | Replay detection via consumed nonce set | P0 | IMPLEMENTED |
| TOK-012 | Token revocation list for compromised tokens | P1 | PARTIAL |
| TOK-013 | Token introspection endpoint | P1 | PARTIAL |
| TOK-014 | Token provenance chain | P1 | PLANNED |
| TOK-015 | Token chain tracking across delegation | P1 | PLANNED |
| TOK-016 | Token misuse anomaly detection | P1 | PLANNED |
| TOK-017 | Cryptographic key rotation without downtime | P1 | PARTIAL |
| TOK-018 | KMS-backed key management | P1 | PARTIAL |
| TOK-019 | HSM-backed key management | P1 | PARTIAL |
| TOK-020 | External signer support (e.g., Cloud KMS) | P1 | PLANNED |
| TOK-021 | Token binding to client certificate | P2 | PLANNED |
| TOK-022 | Token binding to IP address | P2 | PLANNED |
| TOK-023 | Token binding to user-agent | P2 | PLANNED |
| TOK-024 | Token leak detection via unexpected usage patterns | P1 | PLANNED |
| TOK-025 | Token blacklist for revoked tokens | P1 | PARTIAL |
| TOK-026 | Token whitelist for expected tokens | P2 | PLANNED |
| TOK-027 | Token lifetime optimization based on risk | P1 | PLANNED |
| TOK-028 | Token renewal without re-authorization | P2 | PLANNED |
| TOK-029 | Token delegation with attenuated scope | P1 | PARTIAL |
| TOK-030 | Token audit trail with chain of custody | P0 | IMPLEMENTED |

# DOMAIN 04 — RISK ENGINE

| ID | Capability | Priority | Status |
|---|---|---|---|
| RISK-001 | Action risk scoring | P0 | IMPLEMENTED |
| RISK-002 | Blast-radius risk estimation | P1 | PARTIAL |
| RISK-003 | Data sensitivity risk weighting | P1 | PLANNED |
| RISK-004 | Financial impact risk weighting | P1 | PARTIAL |
| RISK-005 | Destructive action risk scoring | P0 | IMPLEMENTED |
| RISK-006 | Privilege escalation risk detection | P0 | IMPLEMENTED |
| RISK-007 | Novelty risk (unusual tool/resource combination) | P1 | PARTIAL |
| RISK-008 | Behavioral risk from agent history | P1 | PARTIAL |
| RISK-009 | Velocity risk (action rate) | P1 | PARTIAL |
| RISK-010 | Repeated-action risk | P0 | IMPLEMENTED |
| RISK-011 | Dependency risk (downstream impact) | P1 | PLANNED |
| RISK-012 | Environment risk (prod vs dev) | P1 | PLANNED |
| RISK-013 | Production environment flag | P1 | PLANNED |
| RISK-014 | Tenant-specific risk scoring | P1 | PLANNED |
| RISK-015 | Cumulative session risk | P1 | PLANNED |
| RISK-016 | Cross-agent risk aggregation | P1 | PLANNED |
| RISK-017 | Tool-specific risk scoring | P1 | PLANNED |
| RISK-018 | Target sensitivity scoring | P1 | PLANNED |
| RISK-019 | Time-based risk (off-hours, holidays) | P1 | PLANNED |
| RISK-020 | Anomaly-adjusted risk (ML-assisted) | P2 | PLANNED |
| RISK-021 | Recovery difficulty estimation | P1 | PLANNED |
| RISK-022 | Recovery confidence integration | P1 | PARTIAL |
| RISK-023 | Irreversible-impact risk pre-assessment | P1 | PLANNED |
| RISK-024 | Risk score caching with TTL | P2 | PLANNED |
| RISK-025 | Risk threshold tuning per tenant | P2 | PLANNED |
| RISK-026 | Risk signal explainability | P0 | IMPLEMENTED |
| RISK-027 | Risk-based adaptive policy | P1 | PLANNED |
| RISK-028 | Risk dashboard with real-time scoring | P2 | PLANNED |
| RISK-029 | Risk heatmap by agent/resource/tool | P2 | PLANNED |
| RISK-030 | Risk trend analysis | P2 | PLANNED |

# DOMAIN 05 — AGENT BEHAVIOR ANALYSIS

| ID | Capability | Priority | Status |
|---|---|---|---|
| BEH-001 | Normal behavior profile per agent | P1 | PLANNED |
| BEH-002 | Session baseline establishment | P1 | PLANNED |
| BEH-003 | Behavioral drift detection | P1 | PLANNED |
| BEH-004 | Action-sequence anomaly detection | P1 | PARTIAL |
| BEH-005 | Unusual tool selection detection | P1 | PARTIAL |
| BEH-006 | Unusual target selection detection | P1 | PLANNED |
| BEH-007 | Unusual action velocity detection | P1 | PARTIAL |
| BEH-008 | Unusual privilege escalation detection | P0 | PARTIAL |
| BEH-009 | Unusual data access pattern detection | P1 | PLANNED |
| BEH-010 | Unexpected chaining detection | P1 | PLANNED |
| BEH-011 | Looping behavior detection | P1 | PLANNED |
| BEH-012 | Recursive behavior detection | P1 | PLANNED |
| BEH-013 | Runaway behavior detection | P0 | PLANNED |
| BEH-014 | Autonomous escalation detection | P1 | PARTIAL |
| BEH-015 | Policy drift detection | P1 | PLANNED |
| BEH-016 | Intent/action mismatch detection | P1 | PLANNED |
| BEH-017 | Behavioral fingerprinting | P2 | PLANNED |
| BEH-018 | Behavioral comparison across agents | P2 | PLANNED |
| BEH-019 | Behavioral anomaly scoring | P1 | PLANNED |
| BEH-020 | Behavioral anomaly alerting | P1 | PLANNED |

# DOMAIN 06 — PROMPT INJECTION DEFENSE

| ID | Capability | Priority | Status |
|---|---|---|---|
| INJ-001 | Direct prompt injection detection | P0 | IMPLEMENTED |
| INJ-002 | Indirect prompt injection via retrieved content | P1 | PARTIAL |
| INJ-003 | Malicious document detection | P1 | PLANNED |
| INJ-004 | Poisoned tool detection | P1 | PLANNED |
| INJ-005 | Poisoned MCP server detection | P1 | PLANNED |
| INJ-006 | Tool-description injection detection | P1 | PLANNED |
| INJ-007 | Instruction hierarchy enforcement | P1 | PARTIAL |
| INJ-008 | Hidden instruction detection (zero-width, steganography) | P0 | PARTIAL |
| INJ-009 | Encoded instruction detection (base64, hex, rot13) | P0 | PARTIAL |
| INJ-010 | Context poisoning detection | P1 | PLANNED |
| INJ-011 | Memory poisoning detection | P1 | PLANNED |
| INJ-012 | Cross-session poisoning prevention | P1 | PLANNED |
| INJ-013 | Agent-to-agent instruction attack detection | P1 | PLANNED |
| INJ-014 | Prompt injection classification taxonomy | P1 | PLANNED |
| INJ-015 | Prompt injection evidence capture | P0 | PARTIAL |
| INJ-016 | Prompt injection containment hooks | P1 | PLANNED |
| INJ-017 | Prompt injection recovery hooks | P1 | PLANNED |
| INJ-018 | Prompt injection replay analysis | P1 | PLANNED |
| INJ-019 | Prompt injection forensic reconstruction | P1 | PLANNED |
| INJ-020 | Prompt injection rate limiting | P1 | PLANNED |
| INJ-021 | Prompt injection blocklist | P1 | PARTIAL |
| INJ-022 | Prompt injection allowlist for trusted sources | P1 | PLANNED |
| INJ-023 | Prompt injection simulation for testing | P1 | PARTIAL |
| INJ-024 | Prompt injection metrics and alerting | P1 | PLANNED |
| INJ-025 | Prompt injection incident correlation | P1 | PLANNED |

# DOMAIN 07 — TOOL SECURITY

| ID | Capability | Priority | Status |
|---|---|---|---|
| TOOL-001 | Tool inventory registry | P1 | PLANNED |
| TOOL-002 | Tool trust score based on history | P1 | PLANNED |
| TOOL-003 | Tool provenance chain | P1 | PLANNED |
| TOOL-004 | Tool permission model | P1 | PARTIAL |
| TOOL-005 | Tool signature verification | P1 | PLANNED |
| TOOL-006 | Tool version tracking | P1 | PLANNED |
| TOOL-007 | Tool reputation system | P2 | PLANNED |
| TOOL-008 | Tool dependency graph | P1 | PLANNED |
| TOOL-009 | Tool sandboxing enforcement | P1 | PLANNED |
| TOOL-010 | Tool allowlist | P1 | PARTIAL |
| TOOL-011 | Tool denylist | P1 | PARTIAL |
| TOOL-012 | Dynamic authorization per tool call | P0 | IMPLEMENTED |
| TOOL-013 | Tool anomaly detection | P1 | PLANNED |
| TOOL-014 | Tool rollback where supported | P1 | PLANNED |
| TOOL-015 | Malicious tool detection | P1 | PARTIAL |
| TOOL-016 | Tool capability declaration | P1 | IMPLEMENTED |
| TOOL-017 | Tool output validation | P1 | PARTIAL |
| TOOL-018 | Tool argument schema validation | P0 | IMPLEMENTED |
| TOOL-019 | Tool rate limiting | P1 | PARTIAL |
| TOOL-020 | Tool usage audit trail | P0 | IMPLEMENTED |

# DOMAIN 08 — MCP SECURITY

| ID | Capability | Priority | Status |
|---|---|---|---|
| MCP-001 | MCP server registry with identity | P1 | PLANNED |
| MCP-002 | MCP server provenance tracking | P1 | PLANNED |
| MCP-003 | MCP tool inventory | P1 | PLANNED |
| MCP-004 | MCP resource inventory | P1 | PLANNED |
| MCP-005 | MCP prompt inventory | P1 | PLANNED |
| MCP-006 | MCP trust levels | P1 | PLANNED |
| MCP-007 | MCP scoped credentials | P1 | PLANNED |
| MCP-008 | MCP authorization at tool/resource level | P1 | PLANNED |
| MCP-009 | MCP argument validation | P1 | PARTIAL |
| MCP-010 | MCP output validation | P1 | PLANNED |
| MCP-011 | MCP data classification | P1 | PLANNED |
| MCP-012 | MCP egress control | P1 | PLANNED |
| MCP-013 | MCP runtime containment | P1 | PLANNED |
| MCP-014 | MCP session replay | P1 | PLANNED |
| MCP-015 | MCP evidence capture | P1 | PLANNED |
| MCP-016 | MCP incident reconstruction | P1 | PLANNED |
| MCP-017 | MCP recovery hooks | P1 | PLANNED |
| MCP-018 | MCP policy simulation | P1 | PLANNED |
| MCP-019 | MCP server health monitoring | P1 | PLANNED |
| MCP-020 | MCP server quarantine | P1 | PLANNED |

# DOMAIN 09 — AGENT-TO-AGENT SECURITY

| ID | Capability | Priority | Status |
|---|---|---|---|
| A2A-001 | Delegation with scope attenuation | P0 | IMPLEMENTED |
| A2A-002 | Multi-agent authority chain | P0 | IMPLEMENTED |
| A2A-003 | Sub-agent creation policy | P1 | PARTIAL |
| A2A-004 | Identity inheritance validation | P1 | PARTIAL |
| A2A-005 | Authority attenuation enforcement | P1 | PARTIAL |
| A2A-006 | Agent communication authorization | P1 | PLANNED |
| A2A-007 | Message authorization between agents | P1 | PLANNED |
| A2A-008 | Agent trust scoring | P1 | PLANNED |
| A2A-009 | Agent reputation system | P2 | PLANNED |
| A2A-010 | Lateral movement detection | P0 | PLANNED |
| A2A-011 | Confused deputy prevention | P0 | PARTIAL |
| A2A-012 | Malicious sub-agent detection | P1 | PLANNED |
| A2A-013 | Compromised sub-agent containment | P0 | IMPLEMENTED |
| A2A-014 | Cascading failure detection | P1 | PLANNED |
| A2A-015 | Cross-agent containment | P0 | IMPLEMENTED |
| A2A-016 | Coordinated recovery across agents | P1 | PLANNED |

# DOMAIN 10 — CONTAINMENT

| ID | Capability | Priority | Status |
|---|---|---|---|
| CNT-001 | Action deny at authorization layer | P0 | IMPLEMENTED |
| CNT-002 | Session freeze enforcement | P1 | PARTIAL |
| CNT-003 | Session quarantine with evidence | P1 | PARTIAL |
| CNT-004 | Agent freeze with state preservation | P1 | PARTIAL |
| CNT-005 | Agent revoke with cascade | P0 | PARTIAL |
| CNT-006 | Token revoke via nonce invalidation | P0 | IMPLEMENTED |
| CNT-007 | Credential revoke workflow | P1 | PLANNED |
| CNT-008 | Tool isolation | P1 | PLANNED |
| CNT-009 | Network isolation hooks | P1 | PLANNED |
| CNT-010 | Workload quarantine | P1 | PARTIAL |
| CNT-011 | Process termination signal | P2 | PLANNED |
| CNT-012 | Environment isolation | P1 | PLANNED |
| CNT-013 | Tenant isolation enforcement | P0 | IMPLEMENTED |
| CNT-014 | Cascading containment with depth limit | P0 | IMPLEMENTED |
| CNT-015 | Emergency global containment mode | P0 | PLANNED |
| CNT-016 | Containment policies (automated triggers) | P1 | PARTIAL |
| CNT-017 | Containment playbooks | P1 | PLANNED |
| CNT-018 | Automatic containment triggers | P1 | PARTIAL |
| CNT-019 | Human-triggered containment with approval | P1 | PARTIAL |
| CNT-020 | Timed quarantine with automatic recovery | P1 | PLANNED |
| CNT-021 | Staged containment (graduated response) | P1 | PLANNED |
| CNT-022 | Containment verification checks | P1 | PARTIAL |
| CNT-023 | Containment evidence preservation | P0 | IMPLEMENTED |
| CNT-024 | Containment replay for forensics | P1 | PLANNED |
| CNT-025 | Containment effectiveness measurement | P1 | PLANNED |
| CNT-026 | Containment blast-radius calculation | P0 | PARTIAL |
| CNT-027 | Containment exception handling | P1 | PLANNED |
| CNT-028 | Containment audit trail | P0 | IMPLEMENTED |
| CNT-029 | Containment notification to affected parties | P1 | PLANNED |
| CNT-030 | Containment recovery coordination | P1 | PLANNED |

# DOMAIN 11 — CHANGE ATTRIBUTION

| ID | Capability | Priority | Status |
|---|---|---|---|
| ATT-001 | Attribute mutation to agent | P0 | IMPLEMENTED |
| ATT-002 | Attribute mutation to session | P0 | IMPLEMENTED |
| ATT-003 | Attribute mutation to intent | P0 | IMPLEMENTED |
| ATT-004 | Attribute mutation to action | P0 | IMPLEMENTED |
| ATT-005 | Attribute mutation to execution token | P1 | PARTIAL |
| ATT-006 | Attribute mutation to tool | P0 | IMPLEMENTED |
| ATT-007 | Attribute mutation to human user | P1 | PARTIAL |
| ATT-008 | Attribute mutation to service | P1 | PARTIAL |
| ATT-009 | Attribute mutation to workflow | P1 | PARTIAL |
| ATT-010 | Attribute mutation to transaction | P1 | PLANNED |
| ATT-011 | Attribute mutation to timestamp (exact) | P0 | IMPLEMENTED |
| ATT-012 | Attribute mutation to environment | P1 | PLANNED |
| ATT-013 | Detect shared changes between agents | P1 | PLANNED |
| ATT-014 | Detect mixed-origin changes | P0 | PARTIAL |
| ATT-015 | Detect human-after-agent changes | P1 | PLANNED |
| ATT-016 | Detect agent-after-human changes | P1 | PLANNED |
| ATT-017 | Detect competing agents on same resource | P1 | PLANNED |
| ATT-018 | Detect concurrent writers | P0 | PARTIAL |
| ATT-019 | Detect ambiguous provenance | P1 | PLANNED |
| ATT-020 | Attribute confidence scoring | P1 | PLANNED |

# DOMAIN 12 — STATE CAPTURE

| ID | Capability | Priority | Status |
|---|---|---|---|
| CAP-001 | Exact byte capture | P1 | PARTIAL |
| CAP-002 | Text-safe capture with encoding | P1 | PARTIAL |
| CAP-003 | Binary-safe capture | P1 | PLANNED |
| CAP-004 | Encoding metadata (utf-8, utf-16, etc.) | P1 | PLANNED |
| CAP-005 | BOM detection and preservation | P1 | PLANNED |
| CAP-006 | LF/CRLF normalization tracking | P1 | PLANNED |
| CAP-007 | File metadata capture (mtime, atime, ctime) | P1 | PARTIAL |
| CAP-008 | Permission state capture (mode, ACL) | P1 | PARTIAL |
| CAP-009 | Ownership capture (uid, gid) | P1 | PARTIAL |
| CAP-010 | ACL capture | P1 | PLANNED |
| CAP-011 | Database row before/after state | P0 | IMPLEMENTED |
| CAP-012 | Table metadata capture | P1 | PARTIAL |
| CAP-013 | Configuration file before/after state | P0 | IMPLEMENTED |
| CAP-014 | Git tree capture | P0 | IMPLEMENTED |
| CAP-015 | Commit ancestry capture | P0 | IMPLEMENTED |
| CAP-016 | Cloud resource state capture | P1 | PLANNED |
| CAP-017 | API state capture | P1 | PLANNED |
| CAP-018 | Object state capture | P1 | PARTIAL |
| CAP-019 | Dependency state capture | P1 | PARTIAL |
| CAP-020 | Schema state capture | P1 | PARTIAL |
| CAP-021 | Version identifiers capture | P1 | PARTIAL |
| CAP-022 | Cryptographic hash of state | P0 | PARTIAL |
| CAP-023 | Merkle proof chain for evidence | P1 | PLANNED |
| CAP-024 | Incremental state capture | P1 | PLANNED |
| CAP-025 | State capture retention policy | P1 | PLANNED |
| CAP-026 | State capture compression | P2 | PLANNED |
| CAP-027 | State capture encryption at rest | P1 | PLANNED |
| CAP-028 | State capture tamper detection | P1 | PLANNED |
| CAP-029 | State capture verification | P0 | PARTIAL |
| CAP-030 | State capture export | P1 | PARTIAL |

# DOMAIN 13 — RECOVERY ENGINE

| ID | Capability | Priority | Status |
|---|---|---|---|
| REC-001 | Filesystem recovery (create/modify/delete/rename) | P0 | IMPLEMENTED |
| REC-002 | Git recovery (commit, working tree, branch) | P0 | IMPLEMENTED |
| REC-003 | Database recovery (INSERT/UPDATE/DELETE) | P0 | IMPLEMENTED |
| REC-004 | Configuration recovery with drift detection | P0 | IMPLEMENTED |
| REC-005 | Cloud resource recovery | P1 | PLANNED |
| REC-006 | Kubernetes workload recovery | P1 | PLANNED |
| REC-007 | Container image/state recovery | P1 | PLANNED |
| REC-008 | Object storage recovery | P1 | PLANNED |
| REC-009 | Message queue recovery | P1 | PLANNED |
| REC-010 | Cache invalidation/recovery | P1 | PLANNED |
| REC-011 | Secrets metadata recovery | P1 | PLANNED |
| REC-012 | Infrastructure-as-code recovery | P1 | PLANNED |
| REC-013 | API object recovery | P1 | PLANNED |
| REC-014 | SaaS object recovery | P2 | PLANNED |
| REC-015 | Ticketing/task recovery | P2 | PLANNED |
| REC-016 | Workflow state recovery | P1 | PARTIAL |
| REC-017 | Financial transaction recovery | P1 | PARTIAL |
| REC-018 | Email metadata recovery | P2 | PLANNED |
| REC-019 | Permission change recovery | P1 | PARTIAL |
| REC-020 | Identity change recovery | P1 | PLANNED |

# DOMAIN 14 — IRREVERSIBLE ACTION HANDLING

| ID | Capability | Priority | Status |
|---|---|---|---|
| IRR-001 | Reversible action classification | P0 | IMPLEMENTED |
| IRR-002 | Compensatable action classification | P0 | IMPLEMENTED |
| IRR-003 | Partially compensatable classification | P1 | PARTIAL |
| IRR-004 | Irreversible action classification | P0 | IMPLEMENTED |
| IRR-005 | Unknown reversibility classification | P0 | IMPLEMENTED |
| IRR-006 | Impact detection for irreversible actions | P1 | PARTIAL |
| IRR-007 | Evidence preservation for irreversible actions | P0 | IMPLEMENTED |
| IRR-008 | Compensation plan for irreversible actions | P1 | PARTIAL |
| IRR-009 | Human escalation for irreversible actions | P0 | IMPLEMENTED |
| IRR-010 | Affected-party notification hooks | P1 | PLANNED |
| IRR-011 | Audit trail for irreversible actions | P0 | IMPLEMENTED |
| IRR-012 | Residual-risk calculation | P1 | PARTIAL |
| IRR-013 | Irreversible action warning to user | P1 | PARTIAL |
| IRR-014 | Dual-approval for irreversible actions | P1 | PLANNED |
| IRR-015 | Time-delay for irreversible actions | P1 | PLANNED |
| IRR-016 | Reversibility re-evaluation after action | P1 | PLANNED |
| IRR-017 | Compensation effectiveness measurement | P1 | PLANNED |
| IRR-018 | Legal hold support for irreversible actions | P2 | PLANNED |

# DOMAIN 15 — RECOVERY PLANNING

| ID | Capability | Priority | Status |
|---|---|---|---|
| PLN-001 | Dependency graph construction | P1 | PARTIAL |
| PLN-002 | Recovery ordering via reverse topological sort | P0 | IMPLEMENTED |
| PLN-003 | Conflict analysis in recovery plan | P0 | IMPLEMENTED |
| PLN-004 | Blast-radius minimization | P1 | PLANNED |
| PLN-005 | Minimal-change recovery planning | P1 | PARTIAL |
| PLN-006 | Maximal-safety recovery planning | P1 | PARTIAL |
| PLN-007 | Alternate recovery plan generation | P1 | PLANNED |
| PLN-008 | Plan comparison and ranking | P1 | PLANNED |
| PLN-009 | Plan scoring model | P1 | PLANNED |
| PLN-010 | Uncertainty representation in plan | P0 | IMPLEMENTED |
| PLN-011 | Rollback boundary definition | P1 | PLANNED |
| PLN-012 | Compensation boundary definition | P1 | PLANNED |
| PLN-013 | Human approval gates in plan | P0 | IMPLEMENTED |
| PLN-014 | Recovery simulation before execution | P0 | IMPLEMENTED |
| PLN-015 | Recovery preview with diff | P1 | PARTIAL |
| PLN-016 | Recovery explanation with rationale | P1 | PARTIAL |
| PLN-017 | Plan immutability after approval | P0 | IMPLEMENTED |
| PLN-018 | Plan versioning | P1 | PARTIAL |
| PLN-019 | Plan audit trail | P0 | IMPLEMENTED |
| PLN-020 | Plan export for external review | P1 | PARTIAL |

# DOMAIN 16 — RECOVERY VERIFICATION

| ID | Capability | Priority | Status |
|---|---|---|---|
| VER-001 | Exact hash verification | P0 | PARTIAL |
| VER-002 | Content comparison (byte-level) | P0 | PARTIAL |
| VER-003 | Structural comparison | P1 | PARTIAL |
| VER-004 | Schema validation | P1 | PARTIAL |
| VER-005 | Database integrity verification | P1 | PARTIAL |
| VER-006 | Foreign-key verification | P1 | PARTIAL |
| VER-007 | Invariant verification | P1 | PLANNED |
| VER-008 | Permission verification | P1 | PARTIAL |
| VER-009 | Dependency verification | P1 | PARTIAL |
| VER-010 | Service-health verification | P1 | PLANNED |
| VER-011 | Application-level verification | P1 | PLANNED |
| VER-012 | Semantic verification | P1 | PLANNED |
| VER-013 | Cross-system consistency verification | P1 | PLANNED |
| VER-014 | Recovery completeness check | P1 | PARTIAL |
| VER-015 | Verification coverage measurement | P1 | PLANNED |
| VER-016 | Confidence scoring for verification | P1 | PARTIAL |
| VER-017 | Residual risk after verification | P1 | PARTIAL |
| VER-018 | Independent verification (separate from execution) | P0 | IMPLEMENTED |
| VER-019 | Verification retry on transient failure | P1 | PLANNED |
| VER-020 | Verification audit trail | P0 | IMPLEMENTED |

# DOMAIN 17 — RECOVERY CONFIDENCE

| ID | Capability | Priority | Status |
|---|---|---|---|
| CNF-001 | Evidence completeness scoring | P1 | PLANNED |
| CNF-002 | State certainty scoring | P1 | PARTIAL |
| CNF-003 | Recovery coverage calculation | P1 | PLANNED |
| CNF-004 | Dependency certainty scoring | P1 | PARTIAL |
| CNF-005 | Conflict status weighting | P0 | IMPLEMENTED |
| CNF-006 | External side-effect accounting | P1 | PARTIAL |
| CNF-007 | Irreversible action accounting | P0 | IMPLEMENTED |
| CNF-008 | Verification coverage scoring | P1 | PLANNED |
| CNF-009 | Adapter reliability weighting | P1 | PARTIAL |
| CNF-010 | Execution certainty scoring | P1 | PARTIAL |
| CNF-011 | Composite confidence score | P1 | PARTIAL |
| CNF-012 | Confidence band (min/expected/max) | P1 | PLANNED |
| CNF-013 | Explanation of confidence factors | P1 | PARTIAL |
| CNF-014 | Unresolved uncertainty enumeration | P1 | PARTIAL |
| CNF-015 | Recommended human action | P0 | IMPLEMENTED |
| CNF-016 | Confidence threshold for auto-approval | P1 | PLANNED |
| CNF-017 | Confidence decay over time | P2 | PLANNED |
| CNF-018 | Confidence adjustment after new evidence | P1 | PLANNED |

# DOMAIN 18 — INCIDENT RESPONSE

| ID | Capability | Priority | Status |
|---|---|---|---|
| INC-001 | Incident detection | P1 | PARTIAL |
| INC-002 | Incident declaration workflow | P1 | PARTIAL |
| INC-003 | Incident containment | P0 | IMPLEMENTED |
| INC-004 | Incident investigation | P1 | PARTIAL |
| INC-005 | Incident reconstruction | P0 | IMPLEMENTED |
| INC-006 | Incident recovery planning | P0 | IMPLEMENTED |
| INC-007 | Incident recovery execution | P0 | IMPLEMENTED |
| INC-008 | Incident verification | P0 | IMPLEMENTED |
| INC-009 | Incident closure | P1 | PARTIAL |
| INC-010 | Lessons-learned capture | P1 | PLANNED |
| INC-011 | Severity classification | P0 | IMPLEMENTED |
| INC-012 | Incident taxonomy/classification | P1 | PARTIAL |
| INC-013 | Incident timeline construction | P0 | IMPLEMENTED |
| INC-014 | Evidence bundle assembly | P1 | PARTIAL |
| INC-015 | Affected resources enumeration | P0 | IMPLEMENTED |
| INC-016 | Affected tenants enumeration | P0 | IMPLEMENTED |
| INC-017 | Root-cause hypothesis generation | P1 | PLANNED |
| INC-018 | Recovery plan linkage | P0 | IMPLEMENTED |
| INC-019 | Recovery status tracking | P1 | PARTIAL |
| INC-020 | Residual risk tracking | P1 | PARTIAL |
| INC-021 | Incident export (JSON, PDF, CSV) | P1 | PARTIAL |
| INC-022 | Incident correlation across tenants | P1 | PLANNED |
| INC-023 | Incident trend analysis | P1 | PLANNED |
| INC-024 | Incident SLA tracking | P1 | PLANNED |
| INC-025 | Incident notification to stakeholders | P1 | PLANNED |
| INC-026 | Incident post-mortem automation | P1 | PLANNED |

# DOMAIN 19 — FORENSICS

| ID | Capability | Priority | Status |
|---|---|---|---|
| FOR-001 | Event timeline reconstruction | P0 | IMPLEMENTED |
| FOR-002 | Action graph construction | P1 | PARTIAL |
| FOR-003 | Causal graph construction | P0 | IMPLEMENTED |
| FOR-004 | Dependency graph reconstruction | P1 | PARTIAL |
| FOR-005 | Token graph reconstruction | P1 | PLANNED |
| FOR-006 | Identity graph reconstruction | P1 | PARTIAL |
| FOR-007 | Tool graph reconstruction | P1 | PLANNED |
| FOR-008 | Resource graph reconstruction | P1 | PLANNED |
| FOR-009 | Mutation graph reconstruction | P1 | PARTIAL |
| FOR-010 | Recovery graph reconstruction | P1 | PLANNED |
| FOR-011 | Incident replay | P1 | PARTIAL |
| FOR-012 | Evidence chain validation | P1 | PARTIAL |
| FOR-013 | Tamper detection for evidence | P1 | PARTIAL |
| FOR-014 | Evidence cryptographic signatures | P1 | PLANNED |
| FOR-015 | Evidence export (forensic package) | P1 | PARTIAL |
| FOR-016 | Forensic snapshot creation | P1 | PLANNED |
| FOR-017 | Forensic snapshot comparison | P1 | PLANNED |
| FOR-018 | Forensic timeline export | P1 | PARTIAL |
| FOR-019 | Forensic report generation | P1 | PLANNED |
| FOR-020 | Legal hold support | P2 | PLANNED |

# DOMAIN 20 — AGENT REPLAY

| ID | Capability | Priority | Status |
|---|---|---|---|
| REP-001 | Intent replay | P1 | PARTIAL |
| REP-002 | Action replay | P1 | PARTIAL |
| REP-003 | Tool call replay | P1 | PARTIAL |
| REP-004 | Policy decision replay | P1 | PARTIAL |
| REP-005 | State transition replay | P1 | PARTIAL |
| REP-006 | Failure replay | P1 | PARTIAL |
| REP-007 | Recovery plan replay | P1 | PARTIAL |
| REP-008 | Verification replay | P1 | PARTIAL |
| REP-009 | Simulation-first replay (no accidental real execution) | P0 | PARTIAL |
| REP-010 | Replay with drift detection | P1 | PLANNED |
| REP-011 | Replay with side-effect isolation | P1 | PLANNED |
| REP-012 | Replay audit trail | P1 | PARTIAL |

# DOMAIN 21 — DIGITAL TWIN / SIMULATION
| ID | Capability | Priority | Status |
|---|---|---|---|
| SIM-001 | Simulated agent environment | P1 | PARTIAL |
| SIM-002 | Simulated tool execution | P1 | PARTIAL |
| SIM-003 | Simulated resource state | P1 | PARTIAL |
| SIM-004 | Simulated filesystem | P1 | PARTIAL |
| SIM-005 | Simulated Git repository | P1 | PARTIAL |
| SIM-006 | Simulated database | P1 | PARTIAL |
| SIM-007 | Simulated REST API | P1 | PARTIAL |
| SIM-008 | Simulated cloud resources | P1 | PLANNED |
| SIM-009 | Simulated failures | P1 | PARTIAL |
| SIM-010 | Simulated conflicts | P1 | PARTIAL |
| SIM-011 | Simulated compromise scenarios | P1 | PARTIAL |
| SIM-012 | Simulated recovery | P0 | IMPLEMENTED |
| SIM-013 | Simulated containment | P1 | PARTIAL |
| SIM-014 | Expected vs Observed vs Recovered comparison | P1 | PARTIAL |
| SIM-015 | Simulation reproducibility | P1 | PLANNED |
| SIM-016 | Simulation scenario library | P1 | PLANNED |
| SIM-017 | Simulation result persistence | P1 | PLANNED |
| SIM-018 | Simulation metrics collection | P1 | PLANNED |

# DOMAIN 22 — AGENT CHAOS ENGINEERING
| ID | Capability | Priority | Status |
|---|---|---|---|
| CHA-001 | Random action failure injection | P1 | PLANNED |
| CHA-002 | Delayed response injection | P1 | PLANNED |
| CHA-003 | Network failure injection | P1 | PLANNED |
| CHA-004 | Permission failure injection | P1 | PARTIAL |
| CHA-005 | Stale state injection | P1 | PARTIAL |
| CHA-006 | Concurrent modification injection | P1 | PARTIAL |
| CHA-007 | Corrupted output injection | P1 | PLANNED |
| CHA-008 | Invalid tool response injection | P1 | PLANNED |
| CHA-009 | Malicious tool simulation | P1 | PARTIAL |
| CHA-010 | Prompt injection simulation | P1 | PARTIAL |
| CHA-011 | Token replay simulation | P0 | IMPLEMENTED |
| CHA-012 | Authority revocation simulation | P1 | PARTIAL |
| CHA-013 | Crash mid-recovery simulation | P1 | PARTIAL |
| CHA-014 | Database conflict injection | P1 | PARTIAL |
| CHA-015 | Filesystem conflict injection | P1 | PARTIAL |
| CHA-016 | Service outage simulation | P1 | PARTIAL |
| CHA-017 | Resilience scoring | P1 | PLANNED |
| CHA-018 | Chaos experiment scheduling | P2 | PLANNED |
| CHA-019 | Chaos experiment audit trail | P1 | PLANNED |
| CHA-020 | Chaos safety controls (blast-radius limits) | P0 | PARTIAL |

# DOMAIN 23 — CONTINUOUS CHECKPOINTING
| ID | Capability | Priority | Status |
|---|---|---|---|
| CHK-001 | Action checkpoints | P0 | IMPLEMENTED |
| CHK-002 | State checkpoints | P0 | PARTIAL |
| CHK-003 | Session checkpoints | P1 | PARTIAL |
| CHK-004 | Transaction checkpoints | P1 | PLANNED |
| CHK-005 | Recovery checkpoints | P0 | PARTIAL |
| CHK-006 | Incremental snapshots | P1 | PLANNED |
| CHK-007 | Checkpoint retention policy | P1 | PLANNED |
| CHK-008 | Checkpoint compression | P2 | PLANNED |
| CHK-009 | Checkpoint verification | P0 | PARTIAL |
| CHK-010 | Checkpoint garbage collection | P1 | PLANNED |
| CHK-011 | Checkpoint encryption at rest | P1 | PLANNED |
| CHK-012 | Checkpoint tamper detection | P1 | PLANNED |
| CHK-013 | Checkpoint import/export | P1 | PLANNED |

# DOMAIN 24 — UNIVERSAL ACTION MODEL
| ID | Capability | Priority | Status |
|---|---|---|---|
| UAM-001 | Canonical read action | P1 | PARTIAL |
| UAM-002 | Canonical write action | P1 | PARTIAL |
| UAM-003 | Canonical create action | P1 | PARTIAL |
| UAM-004 | Canonical update action | P1 | PARTIAL |
| UAM-005 | Canonical delete action | P1 | PARTIAL |
| UAM-006 | Canonical execute action | P1 | PARTIAL |
| UAM-007 | Canonical rename action | P1 | PARTIAL |
| UAM-008 | Canonical move action | P1 | PARTIAL |
| UAM-009 | Canonical permission change action | P1 | PLANNED |
| UAM-010 | Canonical credential change action | P1 | PLANNED |
| UAM-011 | Canonical API call action | P1 | PARTIAL |
| UAM-012 | Canonical database transaction action | P1 | PARTIAL |
| UAM-013 | Canonical infrastructure change action | P1 | PLANNED |
| UAM-014 | Canonical network operation action | P1 | PLANNED |
| UAM-015 | Canonical financial operation action | P1 | PARTIAL |
| UAM-016 | Canonical communication action | P1 | PLANNED |
| UAM-017 | Canonical agent delegation action | P0 | IMPLEMENTED |
| UAM-018 | Adapter translation to canonical model | P1 | PARTIAL |
| UAM-019 | Canonical action serialization format | P1 | PLANNED |
| UAM-020 | Canonical action validation | P1 | PLANNED |

# DOMAIN 25 — RESOURCE GRAPH
| ID | Capability | Priority | Status |
|---|---|---|---|
| RGRAPH-001 | Agent node in resource graph | P1 | PARTIAL |
| RGRAPH-002 | Session node in resource graph | P1 | PARTIAL |
| RGRAPH-003 | User node in resource graph | P1 | PARTIAL |
| RGRAPH-004 | Token node in resource graph | P1 | PARTIAL |
| RGRAPH-005 | Tool node in resource graph | P1 | PLANNED |
| RGRAPH-006 | Resource node in resource graph | P1 | PLANNED |
| RGRAPH-007 | File node in resource graph | P1 | PARTIAL |
| RGRAPH-008 | Repository node in resource graph | P1 | PARTIAL |
| RGRAPH-009 | Database node in resource graph | P1 | PARTIAL |
| RGRAPH-010 | Cloud object node in resource graph | P1 | PLANNED |
| RGRAPH-011 | API node in resource graph | P1 | PLANNED |
| RGRAPH-012 | Service node in resource graph | P1 | PARTIAL |
| RGRAPH-013 | Incident node in resource graph | P1 | PARTIAL |
| RGRAPH-014 | Recovery plan node in resource graph | P1 | PARTIAL |
| RGRAPH-015 | Verification result node | P1 | PLANNED |
| RGRAPH-016 | Edge types (used, modified, created, deleted, depends_on) | P1 | PLANNED |
| RGRAPH-017 | Graph query API | P1 | PLANNED |
| RGRAPH-018 | Graph traversal algorithms | P1 | PLANNED |
| RGRAPH-019 | Graph export (JSON, GraphML) | P1 | PLANNED |
| RGRAPH-020 | Graph visualization data format | P1 | PLANNED |

# DOMAIN 26 — DATA SECURITY
| ID | Capability | Priority | Status |
|---|---|---|---|
| DAT-001 | Sensitive data detection | P1 | PARTIAL |
| DAT-002 | PII detection and classification | P1 | PARTIAL |
| DAT-003 | Secrets detection in data | P1 | PARTIAL |
| DAT-004 | Credential detection in data | P1 | PARTIAL |
| DAT-005 | Token detection in data | P1 | PARTIAL |
| DAT-006 | Regulated data classification | P1 | PLANNED |
| DAT-007 | Data lineage tracking | P1 | PARTIAL |
| DAT-008 | Data egress monitoring | P1 | PLANNED |
| DAT-009 | Tool-output classification | P1 | PLANNED |
| DAT-010 | Agent data access policies | P1 | PLANNED |
| DAT-011 | Data masking for logs | P1 | PLANNED |
| DAT-012 | Data redaction for evidence | P1 | PLANNED |
| DAT-013 | Evidence privacy enforcement | P0 | PARTIAL |
| DAT-014 | Tenant-specific data retention | P1 | PLANNED |
| DAT-015 | Data residency enforcement | P2 | PLANNED |
| DAT-016 | Data encryption at rest | P1 | PARTIAL |
| DAT-017 | Data encryption in transit | P0 | IMPLEMENTED |
| DAT-018 | Data loss prevention hooks | P1 | PLANNED |
| DAT-019 | Data access audit trail | P0 | IMPLEMENTED |
| DAT-020 | Data classification labels | P1 | PLANNED |

# DOMAIN 27 — EXFILTRATION CONTROL
| ID | Capability | Priority | Status |
|---|---|---|---|
| EXF-001 | Unusual outbound destination detection | P1 | PLANNED |
| EXF-002 | Unusual volume detection | P1 | PLANNED |
| EXF-003 | Sensitive data egress detection | P1 | PLANNED |
| EXF-004 | Unexpected domain detection | P1 | PLANNED |
| EXF-005 | Unauthorized upload detection | P1 | PLANNED |
| EXF-006 | Suspicious API call detection | P1 | PARTIAL |
| EXF-007 | Credential leakage detection | P1 | PARTIAL |
| EXF-008 | Encoded payload detection | P0 | PARTIAL |
| EXF-009 | Secret extraction detection | P0 | PARTIAL |
| EXF-010 | Egress rate limiting | P1 | PLANNED |
| EXF-011 | Destination allowlist | P1 | PLANNED |
| EXF-012 | Egress containment | P1 | PLANNED |
| EXF-013 | Exfiltration evidence capture | P1 | PLANNED |
| EXF-014 | Exfiltration alerting | P1 | PLANNED |

# DOMAIN 28 — NETWORK CONTROL
| ID | Capability | Priority | Status |
|---|---|---|---|
| NET-001 | Destination allowlists | P1 | PLANNED |
| NET-002 | Destination policy enforcement | P1 | PLANNED |
| NET-003 | Network risk scoring | P1 | PLANNED |
| NET-004 | DNS monitoring hooks | P1 | PLANNED |
| NET-005 | Egress rules | P1 | PLANNED |
| NET-006 | Service-to-service policy | P1 | PLANNED |
| NET-007 | Network containment | P1 | PLANNED |
| NET-008 | Connection provenance tracking | P1 | PLANNED |
| NET-009 | Network anomaly detection | P1 | PLANNED |
| NET-010 | Emergency network isolation | P0 | PLANNED |

# DOMAIN 29 — CLOUD CONTROL
| ID | Capability | Priority | Status |
|---|---|---|---|
| CLOUD-001 | AWS adapter (IAM, S3, EC2, RDS, Lambda) | P1 | PLANNED |
| CLOUD-002 | Azure adapter (IAM, Blob, VM, SQL, Functions) | P1 | PLANNED |
| CLOUD-003 | GCP adapter (IAM, GCS, GCE, CloudSQL, CloudFunctions) | P1 | PLANNED |
| CLOUD-004 | Cloud IAM policy enforcement | P1 | PLANNED |
| CLOUD-005 | Cloud compute recovery | P1 | PLANNED |
| CLOUD-006 | Cloud storage recovery | P1 | PLANNED |
| CLOUD-007 | Cloud database recovery | P1 | PLANNED |
| CLOUD-008 | Cloud networking recovery | P1 | PLANNED |
| CLOUD-009 | Cloud secrets recovery | P1 | PLANNED |
| CLOUD-010 | Cloud queue recovery | P1 | PLANNED |
| CLOUD-011 | Cloud function recovery | P1 | PLANNED |
| CLOUD-012 | Cloud least-authority enforcement | P1 | PLANNED |
| CLOUD-013 | Cloud drift detection | P1 | PLANNED |
| CLOUD-014 | Cloud audit log integration | P1 | PLANNED |

# DOMAIN 30 — KUBERNETES
| ID | Capability | Priority | Status |
|---|---|---|---|
| K8S-001 | Namespace policy enforcement | P1 | PLANNED |
| K8S-002 | Workload identity binding | P1 | PLANNED |
| K8S-003 | Pod action control | P1 | PLANNED |
| K8S-004 | Exec containment | P1 | PLANNED |
| K8S-005 | Secret access control | P1 | PLANNED |
| K8S-006 | Network policy hooks | P1 | PLANNED |
| K8S-007 | Deployment mutation control | P1 | PLANNED |
| K8S-008 | Admission webhook integration | P1 | PLANNED |
| K8S-009 | Workload quarantine | P1 | PLANNED |
| K8S-010 | Workload rollback | P1 | PLANNED |
| K8S-011 | State capture | P1 | PLANNED |
| K8S-012 | Verification after recovery | P1 | PLANNED |
| K8S-013 | K8s audit log integration | P1 | PLANNED |

# DOMAIN 31 — DATABASE SECURITY & RECOVERY
| ID | Capability | Priority | Status |
|---|---|---|---|
| DB-001 | Row-level attribution | P1 | PARTIAL |
| DB-002 | Transaction provenance | P1 | PLANNED |
| DB-003 | Schema change tracking | P1 | PARTIAL |
| DB-004 | Migration detection | P1 | PLANNED |
| DB-005 | Destructive query detection | P0 | IMPLEMENTED |
| DB-006 | Parameter enforcement | P0 | IMPLEMENTED |
| DB-007 | SQL injection defense | P0 | IMPLEMENTED |
| DB-008 | Transaction boundary awareness | P1 | PARTIAL |
| DB-009 | Concurrent-write handling | P0 | IMPLEMENTED |
| DB-010 | Before-image capture | P0 | IMPLEMENTED |
| DB-011 | After-image capture | P0 | IMPLEMENTED |
| DB-012 | Dependency-aware recovery | P1 | PARTIAL |
| DB-013 | Constraint verification | P1 | PARTIAL |
| DB-014 | Index verification | P1 | PLANNED |
| DB-015 | Trigger awareness | P1 | PLANNED |
| DB-016 | Stored procedure tracking | P1 | PLANNED |
| DB-017 | Database audit log integration | P1 | PLANNED |
| DB-018 | Database encryption at rest | P1 | PARTIAL |
| DB-019 | Database backup verification | P1 | PLANNED |
| DB-020 | Database recovery drill automation | P1 | PLANNED |

# DOMAIN 32 — GIT / CODE RECOVERY
| ID | Capability | Priority | Status |
|---|---|---|---|
| GIT-001 | Commit provenance tracking | P1 | PARTIAL |
| GIT-002 | Branch provenance tracking | P1 | PARTIAL |
| GIT-003 | Agent commit detection | P1 | PARTIAL |
| GIT-004 | Agent push detection | P1 | PARTIAL |
| GIT-005 | PR attribution | P1 | PLANNED |
| GIT-006 | Diff classification | P1 | PARTIAL |
| GIT-007 | Human-change preservation | P0 | IMPLEMENTED |
| GIT-008 | Merge conflict recovery | P1 | PARTIAL |
| GIT-009 | Partial rollback | P0 | IMPLEMENTED |
| GIT-010 | Branch quarantine | P1 | PLANNED |
| GIT-011 | Secret scan after recovery | P1 | PLANNED |
| GIT-012 | Dependency scan | P1 | PLANNED |
| GIT-013 | Build verification after recovery | P1 | PLANNED |
| GIT-014 | Test verification after recovery | P1 | PLANNED |

# DOMAIN 33 — FILESYSTEM
| ID | Capability | Priority | Status |
|---|---|---|---|
| FS-001 | Exact byte capture | P1 | PARTIAL |
| FS-002 | Metadata capture | P1 | PARTIAL |
| FS-003 | Permission state capture | P1 | PARTIAL |
| FS-004 | Ownership capture | P1 | PARTIAL |
| FS-005 | Symlink awareness | P1 | PLANNED |
| FS-006 | Hardlink awareness | P1 | PLANNED |
| FS-007 | Atomic mutation | P1 | PARTIAL |
| FS-008 | Rename recovery | P0 | IMPLEMENTED |
| FS-009 | Move recovery | P1 | PARTIAL |
| FS-010 | Delete recovery | P0 | IMPLEMENTED |
| FS-011 | Recreate recovery | P0 | IMPLEMENTED |
| FS-012 | Binary file handling | P1 | PARTIAL |
| FS-013 | Large file handling | P1 | PARTIAL |
| FS-014 | Conflict detection | P0 | IMPLEMENTED |
| FS-015 | Concurrent modification detection | P1 | PARTIAL |
| FS-016 | Recovery verification | P1 | PARTIAL |
| FS-017 | Path traversal prevention | P0 | IMPLEMENTED |
| FS-018 | Filesystem quarantine | P1 | PLANNED |

# DOMAIN 34 — API SECURITY
| ID | Capability | Priority | Status |
|---|---|---|---|
| API-001 | API action policies | P1 | PARTIAL |
| API-002 | Schema validation | P0 | IMPLEMENTED |
| API-003 | Argument validation | P0 | IMPLEMENTED |
| API-004 | Response validation | P1 | PARTIAL |
| API-005 | Rate controls | P0 | IMPLEMENTED |
| API-006 | Idempotency | P1 | PARTIAL |
| API-007 | Replay prevention | P0 | IMPLEMENTED |
| API-008 | Destination policy | P1 | PLANNED |
| API-009 | Data classification | P1 | PLANNED |
| API-010 | Side-effect classification | P1 | PARTIAL |
| API-011 | Compensating operations | P1 | PARTIAL |
| API-012 | Response evidence capture | P1 | PARTIAL |

# DOMAIN 35 — FINANCIAL / HIGH-IMPACT ACTION CONTROL
| ID | Capability | Priority | Status |
|---|---|---|---|
| FIN-001 | Transaction classification | P1 | PARTIAL |
| FIN-002 | Amount threshold enforcement | P1 | PLANNED |
| FIN-003 | Recipient allowlist | P1 | PLANNED |
| FIN-004 | Approval threshold for high-value | P1 | PLANNED |
| FIN-005 | Velocity threshold enforcement | P1 | PLANNED |
| FIN-006 | Anomaly detection | P1 | PARTIAL |
| FIN-007 | Irreversible-action warnings | P1 | PARTIAL |
| FIN-008 | Dual control | P1 | PLANNED |
| FIN-009 | Human approval required | P0 | IMPLEMENTED |
| FIN-010 | Evidence capture | P1 | PARTIAL |
| FIN-011 | Compensation hooks | P1 | PARTIAL |

# DOMAIN 36 — HUMAN-IN-THE-LOOP
| ID | Capability | Priority | Status |
|---|---|---|---|
| HITL-001 | Approval gates | P0 | IMPLEMENTED |
| HITL-002 | Step-up authentication | P1 | PLANNED |
| HITL-003 | Multi-person approval (M-of-N) | P1 | PARTIAL |
| HITL-004 | Approval expiration | P1 | PLANNED |
| HITL-005 | Approval scope | P1 | PARTIAL |
| HITL-006 | Approval provenance | P0 | IMPLEMENTED |
| HITL-007 | Emergency approval path | P1 | PLANNED |
| HITL-008 | Rejection reason capture | P1 | PLANNED |
| HITL-009 | Escalation path | P1 | PARTIAL |
| HITL-010 | Delegated approval | P1 | PLANNED |
| HITL-011 | Approval audit trail | P0 | IMPLEMENTED |
| HITL-012 | Approval notification | P1 | PLANNED |
| HITL-013 | Approval SLA tracking | P1 | PLANNED |

# DOMAIN 37 — POLICY AS CODE
| ID | Capability | Priority | Status |
|---|---|---|---|
| PAC-001 | Policy language (YAML) | P1 | PARTIAL |
| PAC-002 | Policy schema | P1 | PLANNED |
| PAC-003 | Policy compiler | P1 | PLANNED |
| PAC-004 | Policy validator | P1 | PLANNED |
| PAC-005 | Policy linter | P1 | PLANNED |
| PAC-006 | Policy test framework | P1 | PLANNED |
| PAC-007 | Policy simulator | P1 | PLANNED |
| PAC-008 | Policy versioning | P1 | PARTIAL |
| PAC-009 | Policy diff | P1 | PLANNED |
| PAC-010 | Policy rollback | P1 | PLANNED |
| PAC-011 | Policy deployment workflow | P1 | PLANNED |
| PAC-012 | Policy approval workflow | P1 | PLANNED |
| PAC-013 | Policy registry | P1 | PLANNED |
| PAC-014 | Policy inheritance | P1 | PLANNED |
| PAC-015 | Policy delegation | P1 | PLANNED |

# DOMAIN 38 — POLICY EXPLAINABILITY
| ID | Capability | Priority | Status |
|---|---|---|---|
| EXP-001 | Explain what was requested | P1 | PARTIAL |
| EXP-002 | Explain who requested it | P1 | PARTIAL |
| EXP-003 | Explain applicable policies | P1 | PARTIAL |
| EXP-004 | Explain conditions evaluated | P1 | PARTIAL |
| EXP-005 | Explain risk factors | P0 | IMPLEMENTED |
| EXP-006 | Explain final decision | P0 | IMPLEMENTED |
| EXP-007 | Explain authority used | P1 | PARTIAL |
| EXP-008 | Explain reason for denial | P0 | IMPLEMENTED |
| EXP-009 | Explain expiration | P1 | PARTIAL |
| EXP-010 | Explain recovery plan | P1 | PARTIAL |
| EXP-011 | Explain verification result | P1 | PARTIAL |
| EXP-012 | Explain containment decision | P1 | PARTIAL |
| EXP-013 | Natural language explanation | P1 | PLANNED |
| EXP-014 | Structured explanation format | P1 | PARTIAL |

# DOMAIN 39 — OBSERVABILITY
| ID | Capability | Priority | Status |
|---|---|---|---|
| OBS-001 | Metrics collection | P1 | PARTIAL |
| OBS-002 | Structured logging | P1 | PARTIAL |
| OBS-003 | OpenTelemetry traces | P1 | PLANNED |
| OBS-004 | OpenTelemetry metrics | P1 | PLANNED |
| OBS-005 | OpenTelemetry logs | P1 | PLANNED |
| OBS-006 | Action telemetry | P1 | PARTIAL |
| OBS-007 | Policy telemetry | P1 | PARTIAL |
| OBS-008 | Recovery telemetry | P1 | PARTIAL |
| OBS-009 | Containment telemetry | P1 | PARTIAL |
| OBS-010 | Verification telemetry | P1 | PLANNED |
| OBS-011 | Performance telemetry | P1 | PLANNED |
| OBS-012 | Correlation ID propagation | P0 | IMPLEMENTED |
| OBS-013 | Distributed tracing | P1 | PLANNED |
| OBS-014 | Metrics export (Prometheus) | P1 | PLANNED |
| OBS-015 | Log aggregation integration | P1 | PLANNED |
| OBS-016 | Alerting integration | P1 | PLANNED |
| OBS-017 | Dashboard integration | P1 | PLANNED |

# DOMAIN 40 — SRE / RELIABILITY
| ID | Capability | Priority | Status |
|---|---|---|---|
| SRE-001 | Health check endpoint | P0 | IMPLEMENTED |
| SRE-002 | Readiness check endpoint | P0 | IMPLEMENTED |
| SRE-003 | Liveness check endpoint | P0 | IMPLEMENTED |
| SRE-004 | Dependency health monitoring | P1 | PARTIAL |
| SRE-005 | Queue monitoring | P1 | PLANNED |
| SRE-006 | Timeout controls | P1 | PARTIAL |
| SRE-007 | Retry policy with backoff | P1 | PARTIAL |
| SRE-008 | Circuit breakers | P1 | PLANNED |
| SRE-009 | Backpressure handling | P1 | PLANNED |
| SRE-010 | Graceful degradation | P1 | PARTIAL |
| SRE-011 | Recovery after process crash | P0 | PARTIAL |
| SRE-012 | Recovery after machine crash | P1 | PARTIAL |
| SRE-013 | Durable state persistence | P0 | IMPLEMENTED |
| SRE-014 | Failover support | P1 | PLANNED |
| SRE-015 | Disaster recovery procedure | P1 | PLANNED |
| SRE-016 | Backup verification | P1 | PLANNED |
| SRE-017 | DR drill automation | P1 | PLANNED |
| SRE-018 | SLA monitoring | P1 | PLANNED |
| SRE-019 | Incident escalation automation | P1 | PLANNED |
| SRE-020 | Capacity planning metrics | P2 | PLANNED |

# DOMAIN 41 — DISTRIBUTED RECOVERY
| ID | Capability | Priority | Status |
|---|---|---|---|
| DRC-001 | Durable orchestration | P0 | IMPLEMENTED |
| DRC-002 | Distributed locking | P1 | PARTIAL |
| DRC-003 | Concurrency control | P1 | PARTIAL |
| DRC-004 | Leader election | P1 | PLANNED |
| DRC-005 | Plan recovery after coordinator failure | P0 | PARTIAL |
| DRC-006 | Resume from durable checkpoint | P0 | IMPLEMENTED |
| DRC-007 | Step deduplication | P0 | PARTIAL |
| DRC-008 | Partial failure handling | P0 | IMPLEMENTED |
| DRC-009 | Network partition handling | P1 | PLANNED |
| DRC-010 | Execution leases | P1 | PLANNED |
| DRC-011 | Fencing tokens | P1 | PLANNED |
| DRC-012 | Safe convergence | P1 | PARTIAL |
| DRC-013 | Exactly-once illusion avoided | P0 | IMPLEMENTED |
| DRC-014 | Distributed state transition log | P1 | PLANNED |
| DRC-015 | Multi-region recovery support | P2 | PLANNED |

# DOMAIN 42 — MULTI-TENANCY
| ID | Capability | Priority | Status |
|---|---|---|---|
| TEN-001 | Tenant isolation (data) | P0 | IMPLEMENTED |
| TEN-002 | Tenant isolation (compute) | P1 | PLANNED |
| TEN-003 | Tenant-specific policies | P1 | PARTIAL |
| TEN-004 | Tenant-specific evidence | P0 | IMPLEMENTED |
| TEN-005 | Tenant-specific encryption keys | P1 | PLANNED |
| TEN-006 | Tenant-specific recovery | P0 | IMPLEMENTED |
| TEN-007 | Tenant quotas | P1 | PLANNED |
| TEN-008 | Tenant rate limits | P1 | PLANNED |
| TEN-009 | Tenant configuration | P1 | PLANNED |
| TEN-010 | Tenant audit | P0 | IMPLEMENTED |
| TEN-011 | Tenant export | P1 | PLANNED |
| TEN-012 | Tenant data retention policy | P1 | PLANNED |
| TEN-013 | Cross-tenant attack prevention | P0 | IMPLEMENTED |
| TEN-014 | Tenant onboarding workflow | P1 | PLANNED |
| TEN-015 | Tenant offboarding workflow | P1 | PLANNED |
| TEN-016 | Tenant resource isolation | P1 | PLANNED |

# DOMAIN 43 — ENTERPRISE SECURITY
| ID | Capability | Priority | Status |
|---|---|---|---|
| ENT-001 | SSO integration (production) | P1 | PARTIAL |
| ENT-002 | OIDC integration (production) | P1 | PARTIAL |
| ENT-003 | SAML integration (production) | P1 | PARTIAL |
| ENT-004 | SCIM provisioning | P1 | PLANNED |
| ENT-005 | RBAC with role hierarchy | P1 | PARTIAL |
| ENT-006 | ABAC with attribute policies | P1 | PARTIAL |
| ENT-007 | Enterprise MFA integration | P1 | PARTIAL |
| ENT-008 | Session controls | P1 | PARTIAL |
| ENT-009 | Audit exports (SIEM-ready) | P1 | PARTIAL |
| ENT-010 | Enterprise key management (KMS) | P1 | PARTIAL |
| ENT-011 | HSM integration | P1 | PARTIAL |
| ENT-012 | Certificate rotation | P1 | PLANNED |
| ENT-013 | Secret rotation | P1 | PLANNED |
| ENT-014 | Security headers | P0 | IMPLEMENTED |
| ENT-015 | Secure configuration validation | P1 | PARTIAL |
| ENT-016 | Password policy enforcement | P1 | PARTIAL |
| ENT-017 | Account lockout | P1 | PARTIAL |
| ENT-018 | Brute-force protection | P0 | IMPLEMENTED |
| ENT-019 | API key rotation | P1 | PARTIAL |
| ENT-020 | Security incident notification | P1 | PLANNED |

# DOMAIN 44 — COMPLIANCE EVIDENCE
| ID | Capability | Priority | Status |
|---|---|---|---|
| CMP-001 | Access review evidence | P1 | PARTIAL |
| CMP-002 | Authorization evidence | P1 | PARTIAL |
| CMP-003 | Change attribution evidence | P0 | IMPLEMENTED |
| CMP-004 | Incident evidence | P1 | PARTIAL |
| CMP-005 | Recovery evidence | P0 | IMPLEMENTED |
| CMP-006 | Verification evidence | P1 | PARTIAL |
| CMP-007 | Retention policy export | P1 | PLANNED |
| CMP-008 | Audit trail export | P1 | PARTIAL |
| CMP-009 | Policy history export | P1 | PARTIAL |
| CMP-010 | Administrative activity log | P1 | PARTIAL |
| CMP-011 | SOC 2 evidence package | P2 | PLANNED |
| CMP-012 | ISO 27001 evidence package | P2 | PLANNED |
| CMP-013 | HIPAA evidence package | P2 | PLANNED |
| CMP-014 | PCI-DSS evidence package | P2 | PLANNED |
| CMP-015 | GDPR data-subject request support | P2 | PLANNED |
| CMP-016 | Legal hold support | P2 | PLANNED |
| CMP-017 | Tamper-evident audit storage | P1 | PLANNED |
| CMP-018 | Cryptographic audit logs | P1 | PLANNED |
| CMP-019 | Merkle tree audit log | P1 | PLANNED |
| CMP-020 | Audit log integrity proof | P1 | PLANNED |

# DOMAIN 45 — DASHBOARD
| ID | Capability | Priority | Status |
|---|---|---|---|
| DASH-001 | Agent fleet overview | P2 | PLANNED |
| DASH-002 | Active sessions view | P2 | PLANNED |
| DASH-003 | Authority grants view | P2 | PLANNED |
| DASH-004 | Current risk dashboard | P2 | PLANNED |
| DASH-005 | Blocked actions view | P2 | PLANNED |
| DASH-006 | Incidents overview | P2 | PLANNED |
| DASH-007 | Containment status view | P2 | PLANNED |
| DASH-008 | Recovery status view | P2 | PLANNED |
| DASH-009 | Verification status view | P2 | PLANNED |
| DASH-010 | Evidence browser | P2 | PLANNED |
| DASH-011 | Trend analysis | P2 | PLANNED |
| DASH-012 | Attack pattern visualization | P2 | PLANNED |
| DASH-013 | Resilience score | P2 | PLANNED |
| DASH-014 | Recovery confidence display | P1 | PARTIAL |
| DASH-015 | Executive summary report | P2 | PLANNED |

# DOMAIN 46 — INCIDENT TIMELINE UI
| ID | Capability | Priority | Status |
|---|---|---|---|
| ITUI-001 | Timeline visualization | P2 | PLANNED |
| ITUI-002 | Filter by agent | P2 | PLANNED |
| ITUI-003 | Filter by session | P2 | PLANNED |
| ITUI-004 | Filter by tenant | P2 | PLANNED |
| ITUI-005 | Filter by resource | P2 | PLANNED |
| ITUI-006 | Filter by tool | P2 | PLANNED |
| ITUI-007 | Filter by incident | P2 | PLANNED |
| ITUI-008 | Filter by time range | P2 | PLANNED |
| ITUI-009 | Timeline zoom and pan | P2 | PLANNED |
| ITUI-010 | Timeline export | P2 | PLANNED |

# DOMAIN 47 — RECOVERY WORKBENCH
| ID | Capability | Priority | Status |
|---|---|---|---|
| RW-001 | Recovery plan viewer | P2 | PLANNED |
| RW-002 | Dependency graph visualization | P2 | PLANNED |
| RW-003 | Dry run | P0 | IMPLEMENTED |
| RW-004 | Preview with diff | P1 | PARTIAL |
| RW-005 | Approval workflow | P0 | IMPLEMENTED |
| RW-006 | Execution with progress | P0 | IMPLEMENTED |
| RW-007 | Pause/resume | P1 | PARTIAL |
| RW-008 | Retry failed steps | P1 | PARTIAL |
| RW-009 | Independent verification | P0 | IMPLEMENTED |
| RW-010 | Confidence display | P1 | PARTIAL |
| RW-011 | Residual risk view | P1 | PARTIAL |
| RW-012 | Recovery history | P1 | PLANNED |
| RW-013 | Recovery rollback | P1 | PLANNED |

# DOMAIN 48 — SECURITY RESEARCH MODE
| ID | Capability | Priority | Status |
|---|---|---|---|
| SRS-001 | Fuzzing harness | P1 | PLANNED |
| SRS-002 | Mutation testing | P1 | PLANNED |
| SRS-003 | Attack simulation framework | P1 | PLANNED |
| SRS-004 | Malicious tool simulation | P1 | PARTIAL |
| SRS-005 | Prompt injection simulation | P1 | PARTIAL |
| SRS-006 | Replay simulation | P1 | PARTIAL |
| SRS-007 | Policy abuse testing | P1 | PARTIAL |
| SRS-008 | Token abuse testing | P0 | IMPLEMENTED |
| SRS-009 | Containment test suite | P0 | IMPLEMENTED |
| SRS-010 | Recovery fault injection | P1 | PARTIAL |
| SRS-011 | Research mode isolation | P1 | PLANNED |
| SRS-012 | Research mode audit trail | P1 | PLANNED |

# DOMAIN 49 — ADVERSARIAL TESTING
| ID | Capability | Priority | Status |
|---|---|---|---|
| ADV-001 | Authorization bypass tests | P0 | PARTIAL |
| ADV-002 | Token replay tests | P0 | IMPLEMENTED |
| ADV-003 | Tenant escape tests | P0 | PARTIAL |
| ADV-004 | Confused deputy tests | P0 | PARTIAL |
| ADV-005 | Race condition tests | P1 | PARTIAL |
| ADV-006 | TOCTOU tests | P1 | PARTIAL |
| ADV-007 | Partial failure tests | P1 | PARTIAL |
| ADV-008 | Forged evidence tests | P1 | PARTIAL |
| ADV-009 | Altered snapshot tests | P1 | PARTIAL |
| ADV-010 | Recovery spoofing tests | P1 | PARTIAL |
| ADV-011 | False success tests | P1 | PARTIAL |
| ADV-012 | Malicious tool tests | P1 | PARTIAL |
| ADV-013 | Malicious agent tests | P1 | PARTIAL |
| ADV-014 | Malicious user tests | P1 | PARTIAL |
| ADV-015 | Compromised credential tests | P1 | PARTIAL |
| ADV-016 | Policy bypass tests | P0 | PARTIAL |
| ADV-017 | Containment bypass tests | P0 | PARTIAL |
| ADV-018 | Evidence tampering tests | P1 | PARTIAL |
| ADV-019 | Snapshot tampering tests | P1 | PARTIAL |
| ADV-020 | Recovery plan manipulation tests | P1 | PARTIAL |

# DOMAIN 50 — FORMAL / PROPERTY-BASED SAFETY
| ID | Capability | Priority | Status |
|---|---|---|---|
| PRP-001 | Unauthorized mutation denied | P0 | IMPLEMENTED |
| PRP-002 | Revoked authority cannot authorize | P0 | PARTIAL |
| PRP-003 | Tenant A cannot access tenant B evidence | P0 | IMPLEMENTED |
| PRP-004 | Recovery cannot overwrite unrelated human changes | P0 | IMPLEMENTED |
| PRP-005 | Verification failure cannot produce RECOVERED | P0 | IMPLEMENTED |
| PRP-006 | Immutable evidence remains immutable | P0 | PARTIAL |
| PRP-007 | Recovery plans durable across restart | P0 | IMPLEMENTED |
| PRP-008 | Token replay cannot authorize second execution | P0 | IMPLEMENTED |
| PRP-009 | Property-based test suite (hypothesis) | P1 | PLANNED |
| PRP-010 | Formal invariant documentation | P1 | PLANNED |
| PRP-011 | Invariant automated checking | P1 | PLANNED |
| PRP-012 | Safety property CI enforcement | P1 | PLANNED |

# DOMAIN 51 — PERFORMANCE
| ID | Capability | Priority | Status |
|---|---|---|---|
| PERF-001 | Authorization latency benchmark | P1 | PLANNED |
| PERF-002 | Token verification benchmark | P1 | PLANNED |
| PERF-003 | Action logging benchmark | P1 | PLANNED |
| PERF-004 | Evidence persistence benchmark | P1 | PLANNED |
| PERF-005 | Graph operations benchmark | P1 | PLANNED |
| PERF-006 | Recovery planning benchmark | P1 | PLANNED |
| PERF-007 | Recovery execution benchmark | P1 | PLANNED |
| PERF-008 | Verification benchmark | P1 | PLANNED |
| PERF-009 | Concurrent sessions benchmark | P1 | PLANNED |
| PERF-010 | Multi-tenant benchmark | P1 | PLANNED |
| PERF-011 | Multi-agent benchmark | P1 | PLANNED |
| PERF-012 | Large action dataset benchmark | P1 | PLANNED |
| PERF-013 | Latency measurement (P50/P95/P99) | P1 | PLANNED |
| PERF-014 | Throughput measurement | P1 | PLANNED |
| PERF-015 | CPU profiling | P1 | PLANNED |
| PERF-016 | Memory profiling | P1 | PLANNED |
| PERF-017 | I/O profiling | P1 | PLANNED |
| PERF-018 | Storage growth tracking | P1 | PLANNED |
| PERF-019 | Recovery time measurement | P1 | PLANNED |
| PERF-020 | Verification time measurement | P1 | PLANNED |

# DOMAIN 52 — SCALE
| ID | Capability | Priority | Status |
|---|---|---|---|
| SCALE-001 | 1,000 action workload test | P1 | PLANNED |
| SCALE-002 | 5,000 action workload test | P1 | PLANNED |
| SCALE-003 | 10,000 action workload test | P1 | PLANNED |
| SCALE-004 | 100,000 action workload test | P1 | PLANNED |
| SCALE-005 | 1,000,000 action workload test | P2 | PLANNED |
| SCALE-006 | Concurrent agents stress test | P1 | PLANNED |
| SCALE-007 | Concurrent tenants stress test | P1 | PLANNED |
| SCALE-008 | Concurrent incidents stress test | P1 | PLANNED |
| SCALE-009 | Concurrent recovery plans stress test | P1 | PLANNED |
| SCALE-010 | Database connection pool sizing | P1 | PLANNED |
| SCALE-011 | Redis cluster scalability | P1 | PLANNED |
| SCALE-012 | Read replica support | P2 | PLANNED |
| SCALE-013 | Sharding strategy | P2 | PLANNED |
| SCALE-014 | Partitioning strategy | P2 | PLANNED |
| SCALE-015 | Event streaming (Kafka) integration | P2 | PLANNED |

# DOMAIN 53 — COST OPTIMIZATION
| ID | Capability | Priority | Status |
|---|---|---|---|
| COST-001 | Snapshot storage optimization | P2 | PLANNED |
| COST-002 | Event storage optimization | P2 | PLANNED |
| COST-003 | Graph storage optimization | P2 | PLANNED |
| COST-004 | Log volume optimization | P2 | PLANNED |
| COST-005 | Serialization optimization | P2 | PLANNED |
| COST-006 | Compression for snapshots | P2 | PLANNED |
| COST-007 | Index optimization | P1 | PLANNED |
| COST-008 | Query optimization | P1 | PLANNED |
| COST-009 | Background job optimization | P1 | PLANNED |
| COST-010 | Retry storm prevention | P1 | PARTIAL |
| COST-011 | Checkpoint GC | P1 | PLANNED |
| COST-012 | Cost estimation dashboard | P2 | PLANNED |

# DOMAIN 54 — SDK
| ID | Capability | Priority | Status |
|---|---|---|---|
| SDK-001 | Typed Python client | P1 | PARTIAL |
| SDK-002 | Safer defaults | P1 | PARTIAL |
| SDK-003 | Async support | P1 | PLANNED |
| SDK-004 | Retry logic | P1 | PLANNED |
| SDK-005 | Idempotency helpers | P1 | PARTIAL |
| SDK-006 | Tracing integration | P1 | PLANNED |
| SDK-007 | Structured error types | P1 | PARTIAL |
| SDK-008 | Policy helpers | P1 | PLANNED |
| SDK-009 | Recovery helpers | P1 | PLANNED |
| SDK-010 | Incident helpers | P1 | PLANNED |
| SDK-011 | Simulation helpers | P1 | PLANNED |
| SDK-012 | Testing helpers | P1 | PARTIAL |
| SDK-013 | TypeScript SDK | P2 | PLANNED |
| SDK-014 | Go SDK | P2 | PLANNED |
| SDK-015 | Java SDK | P2 | PLANNED |

# DOMAIN 55 — CLI
| ID | Capability | Priority | Status |
|---|---|---|---|
| CLI-001 | Agent management commands | P1 | PLANNED |
| CLI-002 | Session management commands | P1 | PLANNED |
| CLI-003 | Authority management commands | P1 | PLANNED |
| CLI-004 | Policy management commands | P1 | PLANNED |
| CLI-005 | Action inspection commands | P1 | PLANNED |
| CLI-006 | Incident management commands | P1 | PLANNED |
| CLI-007 | Evidence inspection commands | P1 | PLANNED |
| CLI-008 | Recovery management commands | P1 | PLANNED |
| CLI-009 | Simulation commands | P1 | PLANNED |
| CLI-010 | Benchmark commands | P1 | PLANNED |
| CLI-011 | Diagnostic commands | P1 | PLANNED |
| CLI-012 | CLI shell completion | P2 | PLANNED |
| CLI-013 | CLI configuration profiles | P2 | PLANNED |
| CLI-014 | CLI scripting mode | P2 | PLANNED |
| CLI-015 | CLI plugin system | P2 | PLANNED |

# DOMAIN 56 — DEVELOPER EXPERIENCE
| ID | Capability | Priority | Status |
|---|---|---|---|
| DX-001 | 5-minute installation | P1 | PLANNED |
| DX-002 | 10-minute protected-agent demo | P1 | PLANNED |
| DX-003 | 30-minute integration guide | P1 | PLANNED |
| DX-004 | Simple migration guide | P1 | PLANNED |
| DX-005 | Excellent error messages | P1 | PARTIAL |
| DX-006 | Excellent documentation | P1 | PARTIAL |
| DX-007 | Code examples | P1 | PARTIAL |
| DX-008 | Integration templates | P1 | PLANNED |
| DX-009 | Test harness | P1 | PARTIAL |
| DX-010 | Local development stack | P1 | PARTIAL |
| DX-011 | Troubleshooting guide | P1 | PLANNED |
| DX-012 | Debugging utilities | P1 | PARTIAL |
| DX-013 | Interactive API docs | P0 | IMPLEMENTED |
| DX-014 | SDK quickstart | P1 | PARTIAL |
| DX-015 | Plugin scaffolding | P2 | PLANNED |

# DOMAIN 57 — DOCUMENTATION
| ID | Capability | Priority | Status |
|---|---|---|---|
| DOC-001 | Architecture documentation | P0 | IMPLEMENTED |
| DOC-002 | Security model documentation | P0 | IMPLEMENTED |
| DOC-003 | Threat model documentation | P0 | IMPLEMENTED |
| DOC-004 | Recovery model documentation | P0 | IMPLEMENTED |
| DOC-005 | Adapter guide | P0 | IMPLEMENTED |
| DOC-006 | SDK guide | P1 | PARTIAL |
| DOC-007 | Deployment guide | P1 | PARTIAL |
| DOC-008 | Production checklist | P1 | PARTIAL |
| DOC-009 | Incident response guide | P1 | PARTIAL |
| DOC-010 | Integration guide | P1 | PARTIAL |
| DOC-011 | Migration guide | P1 | PLANNED |
| DOC-012 | Limitations documentation | P0 | IMPLEMENTED |
| DOC-013 | Known risks documentation | P1 | PLANNED |
| DOC-014 | Benchmark methodology | P1 | PLANNED |
| DOC-015 | API reference (auto-generated) | P1 | PARTIAL |
| DOC-016 | Code comments and docstrings | P1 | PARTIAL |
| DOC-017 | Video tutorials | P2 | PLANNED |
| DOC-018 | FAQ | P2 | PLANNED |
| DOC-019 | Glossary | P2 | PLANNED |
| DOC-020 | Change log | P1 | PARTIAL |

# DOMAIN 58 — OPEN TELEMETRY / INTEROPERABILITY
| ID | Capability | Priority | Status |
|---|---|---|---|
| OTLP-001 | OpenTelemetry trace integration | P1 | PLANNED |
| OTLP-002 | OpenTelemetry metrics integration | P1 | PLANNED |
| OTLP-003 | OpenTelemetry logs integration | P1 | PLANNED |
| OTLP-004 | Standard trace format | P1 | PLANNED |
| OTLP-005 | Standard metrics format | P1 | PLANNED |
| OTLP-006 | Standard log format | P1 | PARTIAL |
| OTLP-007 | Resource metadata propagation | P1 | PLANNED |
| OTLP-008 | Correlation ID propagation | P0 | IMPLEMENTED |
| OTLP-009 | Trace context propagation | P1 | PLANNED |
| OTLP-010 | OTLP exporter | P1 | PLANNED |

# DOMAIN 59 — AGENT FRAMEWORK INTEGRATION
| ID | Capability | Priority | Status |
|---|---|---|---|
| FW-001 | OpenAI agents integration | P2 | PLANNED |
| FW-002 | Anthropic agents integration | P2 | PLANNED |
| FW-003 | LangGraph adapter | P1 | PARTIAL |
| FW-004 | LangChain adapter | P0 | IMPLEMENTED |
| FW-005 | CrewAI adapter | P2 | PLANNED |
| FW-006 | AutoGen adapter | P2 | PLANNED |
| FW-007 | OpenHands adapter | P2 | PLANNED |
| FW-008 | Generic tool wrapper SDK | P1 | PLANNED |
| FW-009 | Framework-agnostic agent identity | P1 | PLANNED |
| FW-010 | Framework interoperability guide | P1 | PLANNED |

# DOMAIN 60 — A2A / AGENT PROTOCOLS
| ID | Capability | Priority | Status |
|---|---|---|---|
| A2AP-001 | A2A identity protocol | P1 | PLANNED |
| A2AP-002 | A2A authorization protocol | P1 | PLANNED |
| A2AP-003 | A2A message policy | P1 | PLANNED |
| A2AP-004 | A2A trust model | P1 | PLANNED |
| A2AP-005 | A2A provenance | P1 | PARTIAL |
| A2AP-006 | A2A delegation | P0 | IMPLEMENTED |
| A2AP-007 | A2A evidence | P1 | PARTIAL |
| A2AP-008 | A2A containment | P1 | PARTIAL |
| A2AP-009 | A2A incident reconstruction | P1 | PARTIAL |
| A2AP-010 | A2A recovery hooks | P1 | PARTIAL |

# DOMAIN 61 — WEB / BROWSER AGENTS
| ID | Capability | Priority | Status |
|---|---|---|---|
| WEB-001 | Navigation control | P2 | PLANNED |
| WEB-002 | Form submission control | P2 | PLANNED |
| WEB-003 | Download control | P2 | PLANNED |
| WEB-004 | Upload control | P2 | PLANNED |
| WEB-005 | Browser credential control | P2 | PLANNED |
| WEB-006 | External side-effect classification | P1 | PARTIAL |
| WEB-007 | Sensitive destination policy | P1 | PLANNED |
| WEB-008 | Payment flow control | P1 | PARTIAL |
| WEB-009 | Destructive action detection | P1 | PARTIAL |
| WEB-010 | Browser session isolation | P1 | PLANNED |

# DOMAIN 62 — COMPUTER-USE AGENTS
| ID | Capability | Priority | Status |
|---|---|---|---|
| CU-001 | Screen interaction control | P2 | PLANNED |
| CU-002 | Mouse action control | P2 | PLANNED |
| CU-003 | Keyboard action control | P2 | PLANNED |
| CU-004 | File dialog control | P2 | PLANNED |
| CU-005 | Clipboard control | P2 | PLANNED |
| CU-006 | Application launch control | P2 | PLANNED |
| CU-007 | Privileged operation control | P1 | PLANNED |
| CU-008 | Computer-use containment | P1 | PLANNED |

# DOMAIN 63 — MEMORY SAFETY
| ID | Capability | Priority | Status |
|---|---|---|---|
| MEM-001 | Long-term memory protection | P1 | PLANNED |
| MEM-002 | Session memory isolation | P1 | PARTIAL |
| MEM-003 | Vector store security | P1 | PLANNED |
| MEM-004 | Retrieved context validation | P1 | PARTIAL |
| MEM-005 | Memory write authorization | P1 | PLANNED |
| MEM-006 | Memory deletion authorization | P1 | PLANNED |
| MEM-007 | Memory poisoning detection | P1 | PLANNED |
| MEM-008 | Cross-tenant memory isolation | P1 | PLANNED |
| MEM-009 | Memory audit trail | P1 | PLANNED |
| MEM-010 | Memory retention policy | P1 | PLANNED |

# DOMAIN 64 — AGENT SUPPLY CHAIN
| ID | Capability | Priority | Status |
|---|---|---|---|
| SUP-001 | Model provenance tracking | P1 | PLANNED |
| SUP-002 | System prompt versioning | P1 | PARTIAL |
| SUP-003 | Tool provenance tracking | P1 | PLANNED |
| SUP-004 | Plugin provenance tracking | P1 | PLANNED |
| SUP-005 | MCP server provenance | P1 | PLANNED |
| SUP-006 | Package SBOM generation | P1 | PLANNED |
| SUP-007 | Dependency graph | P1 | PLANNED |
| SUP-008 | Version tracking | P1 | PARTIAL |
| SUP-009 | Configuration provenance | P1 | PARTIAL |
| SUP-010 | Policy version tracking | P1 | PARTIAL |
| SUP-011 | Reproducible agent build | P1 | PLANNED |
| SUP-012 | Supply chain attestation | P1 | PLANNED |

# DOMAIN 65 — MODEL / MODEL-ROUTING SECURITY
| ID | Capability | Priority | Status |
|---|---|---|---|
| MDL-001 | Model identity tracking | P1 | PLANNED |
| MDL-002 | Model version tracking | P1 | PLANNED |
| MDL-003 | Model provider tracking | P1 | PLANNED |
| MDL-004 | Model change detection | P1 | PLANNED |
| MDL-005 | Routing decision logging | P1 | PLANNED |
| MDL-006 | Fallback model policy | P1 | PLANNED |
| MDL-007 | Model-specific permissions | P1 | PLANNED |
| MDL-008 | Model-specific policies | P1 | PLANNED |
| MDL-009 | Model-specific incident tracking | P1 | PLANNED |
| MDL-010 | Model output validation | P1 | PLANNED |

# DOMAIN 66 — INCIDENT AI ASSISTANT
| ID | Capability | Priority | Status |
|---|---|---|---|
| AIA-001 | Incident summarization | P2 | PLANNED |
| AIA-002 | Timeline reconstruction assistance | P1 | PARTIAL |
| AIA-003 | Root-cause hypothesis proposal | P2 | PLANNED |
| AIA-004 | Risk explanation | P1 | PARTIAL |
| AIA-005 | Recovery candidate suggestions | P2 | PLANNED |
| AIA-006 | Uncertainty identification | P1 | PARTIAL |
| AIA-007 | Verification check suggestions | P1 | PLANNED |
| AIA-008 | Human-in-the-loop for AI suggestions | P0 | PARTIAL |
| AIA-009 | AI suggestion audit trail | P1 | PLANNED |
| AIA-010 | AI suggestion explainability | P1 | PLANNED |

# DOMAIN 67 — AI-ASSISTED RECOVERY PLANNING
| ID | Capability | Priority | Status |
|---|---|---|---|
| AIR-001 | Dependency discovery assistance | P1 | PARTIAL |
| AIR-002 | Recovery candidate ranking | P1 | PLANNED |
| AIR-003 | Compensation suggestions | P1 | PARTIAL |
| AIR-004 | Anomaly explanation | P1 | PARTIAL |
| AIR-005 | Incident summarization assistance | P2 | PLANNED |
| AIR-006 | Deterministic safety gates | P0 | IMPLEMENTED |
| AIR-007 | AI suggestion explainability | P1 | PLANNED |

# DOMAIN 68 — SELF-PROTECTION

| ID | Capability | Priority | Status |
|---|---|---|---|
| SELF-001 | Configuration tampering protection | P1 | PLANNED |
| SELF-002 | Policy tampering protection | P1 | PARTIAL |
| SELF-003 | Evidence tampering protection | P1 | PARTIAL |
| SELF-004 | Token manipulation protection | P0 | IMPLEMENTED |
| SELF-005 | Unauthorized admin access prevention | P1 | PARTIAL |
| SELF-006 | Recovery plan manipulation prevention | P1 | PARTIAL |
| SELF-007 | Tenant escape prevention | P0 | IMPLEMENTED |
| SELF-008 | Log destruction prevention | P1 | PARTIAL |
| SELF-009 | Verification disabling prevention | P1 | PARTIAL |
| SELF-010 | Containment disabling prevention | P1 | PARTIAL |
| SELF-011 | Integrity self-check | P1 | PLANNED |
| SELF-012 | Secure bootstrapping | P1 | PLANNED |
| SELF-013 | Runtime integrity monitoring | P1 | PLANNED |

# DOMAIN 69 — ADMINISTRATIVE SAFETY

| ID | Capability | Priority | Status |
|---|---|---|---|
| ADM-001 | Re-authentication for admin actions | P1 | PLANNED |
| ADM-002 | Multi-approver for critical admin | P1 | PLANNED |
| ADM-003 | Explicit confirmation for destructive actions | P1 | PLANNED |
| ADM-004 | Admin action audit trail | P0 | IMPLEMENTED |
| ADM-005 | Reason codes for admin actions | P1 | PARTIAL |
| ADM-006 | Break-glass security mode | P1 | PLANNED |
| ADM-007 | Emergency mode with enhanced logging | P1 | PLANNED |
| ADM-008 | Admin action time-limited authorization | P1 | PLANNED |
| ADM-009 | Admin action notification | P1 | PLANNED |
| ADM-010 | Admin action rollback | P1 | PLANNED |

# DOMAIN 70 — FEATURE GOVERNANCE

| ID | Capability | Priority | Status |
|---|---|---|---|
| GOV-001 | Feature flag framework | P1 | PLANNED |
| GOV-002 | Maturity state tracking | P1 | PARTIAL |
| GOV-003 | Experimental/production designation | P1 | PARTIAL |
| GOV-004 | Documentation requirement enforcement | P1 | PLANNED |
| GOV-005 | Test suite requirement | P0 | IMPLEMENTED |
| GOV-006 | Security review tracking | P1 | PARTIAL |
| GOV-007 | Rollback strategy | P1 | PLANNED |
| GOV-008 | Feature deprecation policy | P2 | PLANNED |
| GOV-009 | Feature usage telemetry | P1 | PLANNED |
| GOV-010 | Feature access control | P1 | PLANNED |

# DOMAIN 71 — SECRETS MANAGEMENT

| ID | Capability | Priority | Status |
|---|---|---|---|
| SEC-001 | Secret inventory | P1 | PLANNED |
| SEC-002 | Secret rotation | P1 | PLANNED |
| SEC-003 | Secret versioning | P1 | PLANNED |
| SEC-004 | Secret access audit | P1 | PLANNED |
| SEC-005 | Secret leak detection | P1 | PLANNED |
| SEC-006 | Secret encryption at rest | P1 | PARTIAL |
| SEC-007 | Secret zero-knowledge storage | P2 | PLANNED |
| SEC-008 | Secret break-glass access | P1 | PLANNED |
| SEC-009 | Secret expiration | P1 | PLANNED |
| SEC-010 | Secret policy enforcement | P1 | PLANNED |

# DOMAIN 72 — CERTIFICATE LIFECYCLE

| ID | Capability | Priority | Status |
|---|---|---|---|
| CERT-001 | Certificate inventory | P2 | PLANNED |
| CERT-002 | Certificate rotation | P1 | PLANNED |
| CERT-003 | Certificate expiry monitoring | P1 | PLANNED |
| CERT-004 | Certificate revocation | P1 | PLANNED |
| CERT-005 | Certificate transparency integration | P2 | PLANNED |
| CERT-006 | Certificate pinning | P1 | PLANNED |
| CERT-007 | Certificate audit trail | P1 | PLANNED |
| CERT-008 | Self-signed certificate support | P1 | PLANNED |
| CERT-009 | Private CA integration | P2 | PLANNED |
| CERT-010 | Certificate emergency rotation | P1 | PLANNED |

# DOMAIN 73 — IDENTITY FEDERATION

| ID | Capability | Priority | Status |
|---|---|---|---|
| FED-001 | OIDC federation | P1 | PARTIAL |
| FED-002 | SAML federation | P1 | PARTIAL |
| FED-003 | LDAP federation | P2 | PLANNED |
| FED-004 | Active Directory federation | P2 | PLANNED |
| FED-005 | Cross-domain identity mapping | P2 | PLANNED |
| FED-006 | Federation trust scoring | P2 | PLANNED |
| FED-007 | Federation audit trail | P1 | PARTIAL |
| FED-008 | Federation incident correlation | P2 | PLANNED |
| FED-009 | Federation policy inheritance | P2 | PLANNED |
| FED-010 | Federation user provisioning | P2 | PLANNED |

# DOMAIN 74 — DEVICE TRUST

| ID | Capability | Priority | Status |
|---|---|---|---|
| DEV-001 | Device identity | P1 | PLANNED |
| DEV-002 | Device posture checking | P1 | PLANNED |
| DEV-003 | Device trust scoring | P1 | PLANNED |
| DEV-004 | Device compliance enforcement | P1 | PLANNED |
| DEV-005 | Device certificate binding | P1 | PLANNED |
| DEV-006 | Device inventory | P1 | PLANNED |
| DEV-007 | Device quarantine | P1 | PLANNED |
| DEV-008 | Device audit trail | P1 | PLANNED |
| DEV-009 | Device risk scoring | P1 | PLANNED |
| DEV-010 | Device attestation | P1 | PLANNED |

# DOMAIN 75 — SUPPLY CHAIN SECURITY

| ID | Capability | Priority | Status |
|---|---|---|---|
| SCS-001 | Dependency SBOM generation | P1 | PLANNED |
| SCS-002 | Dependency vulnerability scanning | P1 | PLANNED |
| SCS-003 | Dependency integrity verification | P1 | PLANNED |
| SCS-004 | Package provenance verification | P1 | PLANNED |
| SCS-005 | Build reproducibility verification | P1 | PLANNED |
| SCS-006 | Software signature verification | P1 | PLANNED |
| SCS-007 | Build pipeline security | P1 | PLANNED |
| SCS-008 | CI/CD security integration | P1 | PLANNED |
| SCS-009 | Artifact signing | P1 | PLANNED |
| SCS-010 | Supply chain attack detection | P1 | PLANNED |
