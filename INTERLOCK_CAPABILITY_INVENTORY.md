# Interlock V4 — Capability Inventory

## Purpose
This inventory records what Interlock V4 already implements, what exists only partially, and what is missing. It is the factual basis for the 1000+ capability roadmap.

## Methodology
- Read-only repository inspection only. No files were modified during this inventory.
- Capabilities are classified as:
  - `IMPLEMENTED` — production-validated or clearly functional
  - `PARTIAL` — scaffold exists but not production-ready
  - `MISSING` — no implementation found
  - `DUPLICATED` — multiple overlapping implementations
  - `UNSAFE` — present but weakens security, recovery, or verification
  - `OBSOLETE` — legacy path superseded elsewhere

## Inventory by Domain

### 01 — Identity & Agent Identity
| Capability | Status | Notes |
|---|---|---|
| Cryptographic agent identity | IMPLEMENTED | Agent entity with agent_id, parent_agent_id, trust levels |
| Session-bound identity | IMPLEMENTED | AgentSession entity, session lifecycle |
| Workload identity | PARTIAL | service_id exists in DTOs; no workload-identity binding enforcement |
| Identity inheritance | PARTIAL | parent_agent_id present; no automatic lineage propagation to tokens |
| Delegated identity | IMPLEMENTED | Authority grants support delegation chain |
| Identity expiration | PARTIAL | expires_at on grants; no global identity TTL |
| Identity rotation | MISSING | No agent identity rotation workflow |
| Identity provenance | PARTIAL | discovery_event exists; limited provenance chain |
| Identity confidence | PARTIAL | TrustLevel enum exists; no confidence scoring |
| Identity anomaly detection | MISSING | No identity anomaly service |
| Identity impersonation detection | MISSING | No impersonation detection |
| Identity revocation | PARTIAL | AgentStatus.QUARANTINED exists; no revoke lifecycle |
| Identity quarantine | IMPLEMENTED | CascadeContainmentService quarantines agents |
| Identity lineage | PARTIAL | authority_lineage_service handles grants; agent lineage limited |
| Cross-system identity mapping | MISSING | No cross-system identity mapper |
| Identity federation | PARTIAL | SSO adapters exist but return mock data |
| Human-to-agent attribution | PARTIAL | owner_user_id on Agent; limited attribution propagation |
| Agent-to-agent attribution | PARTIAL | parent_agent_id; no full attribution graph |
| Sub-agent identity | PARTIAL | parent_agent_id; no sub-agent scoped identity enforcement |
| Tool identity | PARTIAL | tool name tracked; no tool identity registry |
| Execution identity | PARTIAL | execution token carries agent_id, tool; no execution-environment identity |

### 02 — Authorization
| Capability | Status | Notes |
|---|---|---|
| Agent authorization | IMPLEMENTED | AuthorizationService + CentralPolicyEngine |
| Session authorization | PARTIAL | Session entity exists; session-scoped policy limited |
| Task authorization | MISSING | No task-scoped authorization |
| Intent authorization | IMPLEMENTED | IntentEvaluatorService + verify endpoint |
| Tool authorization | IMPLEMENTED | ToolArgumentValidator + tool security |
| Resource authorization | PARTIAL | resource field present; resource-scoped policy limited |
| Action authorization | IMPLEMENTED | ActionControlService evaluation pipeline |
| Parameter authorization | PARTIAL | argument validation exists; parameter-level allow/deny lists limited |
| Environment authorization | PARTIAL | environment awareness limited |
| Tenant authorization | IMPLEMENTED | tenant_id enforced throughout |
| Time-based authorization | PARTIAL | expires_at on grants; no time-of-day/day-of-week policy |
| Geography authorization | MISSING | No geo-based authorization |
| Data classification authorization | MISSING | No data classification tags |
| Risk-based authorization | IMPLEMENTED | RiskEngine scores actions |
| Previous-behavior authorization | PARTIAL | recent_actions passed to risk engine |
| Approval-state authorization | IMPLEMENTED | HITL approval queue |
| Dependency-state authorization | MISSING | No dependency-aware authorization |
| Incident-state authorization | MISSING | No incident-state-aware policy |
| Recovery-state authorization | MISSING | No recovery-state-aware policy |
| Policy simulation | MISSING | No policy simulation API |
| Policy explanation | PARTIAL | explanations returned; no structured explainability model |
| Policy versioning | PARTIAL | policy_version field exists; no versioned policy store |
| Policy diff | MISSING | No policy diff capability |
| Policy testing | MISSING | No policy test framework |
| Policy linting | MISSING | No policy linter |
| Policy conflict analysis | MISSING | No conflict detection across rules |
| Policy inheritance | MISSING | No hierarchical policy inheritance |
| Policy delegation | MISSING | No policy delegation model |
| Policy expiration | MISSING | No policy TTL/expiration |
| Emergency deny | PARTIAL | global deny via policy; no emergency deny API |
| Emergency allow | MISSING | No emergency allow with controls |
| Conditional authority | PARTIAL | conditions dict on grants; no runtime condition evaluator |
| Step-up approval | PARTIAL | HITL exists; no step-up MFA/elevation |
| Just-in-time privilege | MISSING | No JIT provisioning |
| One-shot authority | IMPLEMENTED | Execution tokens are single-use |
| Authority chaining | IMPLEMENTED | delegation_depth + parent_grant_id |
| Authority attenuation | PARTIAL | scope normalization exists; no attenuation enforcement |
| Authority lineage | IMPLEMENTED | AuthorityLineageService |
| Authority replay detection | PARTIAL | nonce replay detection for tokens; grant replay not tracked |

### 03 — Execution Tokens
| Capability | Status | Notes |
|---|---|---|
| Token binding | IMPLEMENTED | Ed25519-signed JWTs with claims |
| Token expiration | IMPLEMENTED | exp, nbf validation |
| Token nonce/JTI | IMPLEMENTED | jti with atomic Redis nonce consumption |
| Audience restriction | MISSING | No aud claim enforcement |
| Action restriction | IMPLEMENTED | tool, action encoded in token |
| Resource restriction | PARTIAL | resource in DTO; not enforced in token claims |
| Parameter restriction | MISSING | No parameter hash/binding in token |
| Session restriction | PARTIAL | agent_id + session awareness; no session binding |
| Tenant restriction | PARTIAL | tenant_id in context; not always enforced in token claims |
| Context binding | PARTIAL | correlation_id propagated; no full context binding |
| Replay detection | IMPLEMENTED | atomic nonce consumption |
| Token revocation | PARTIAL | no revocation list; Redis failure closes |
| Token introspection | PARTIAL | peek_execution_token exists; no full introspection API |
| Token provenance | PARTIAL | jti tracked; no provenance chain |
| Token chain tracking | MISSING | No token chain/cascade tracking |
| Token misuse detection | MISSING | No misuse anomaly detection |
| Cryptographic rotation | PARTIAL | versioned key manager exists; no auto-rotation |
| KMS support | PARTIAL | interface only |
| HSM support | PARTIAL | interface only |
| External signer support | MISSING | No external signer integration |

### 04 — Risk Engine
| Capability | Status | Notes |
|---|---|---|
| Action risk | IMPLEMENTED | RiskEngine evaluates actions |
| Blast-radius risk | PARTIAL | blast_radius field on Incident; no pre-execution blast-radius risk |
| Data risk | MISSING | No data-sensitivity risk weighting |
| Financial risk | PARTIAL | transfer patterns detected; no financial-risk model |
| Destructive risk | PARTIAL | destructive SQL patterns; limited destructive-action taxonomy |
| Privilege risk | PARTIAL | admin-scope escalation detection |
| Novelty risk | PARTIAL | unusual_tool_combination |
| Behavioral risk | PARTIAL | repeated failures, abnormal rate |
| Velocity risk | PARTIAL | abnormal rate signal |
| Repeated-action risk | IMPLEMENTED | repeated_failures signal |
| Dependency risk | MISSING | No dependency-aware risk |
| Environment risk | MISSING | No environment risk weighting |
| Production risk | MISSING | No production environment flag |
| Tenant risk | MISSING | No tenant risk scoring |
| Cumulative session risk | MISSING | No cumulative session risk tracker |
| Cross-agent risk | MISSING | No cross-agent risk aggregation |
| Tool risk | PARTIAL | tool_security exists; no risk scoring per tool |
| Target sensitivity | MISSING | No target sensitivity scoring |
| Time-based risk | MISSING | No time-of-day risk |
| Anomaly-adjusted risk | PARTIAL | risk engine uses anomaly signals; no ML adjustment |
| Recovery difficulty | MISSING | No recovery difficulty estimator |
| Recovery confidence | PARTIAL | recovery_confidence_model exists; not integrated into risk |
| Irreversible-impact risk | MISSING | No irreversible-impact pre-assessment |

### 05 — Agent Behavior Analysis
| Capability | Status | Notes |
|---|---|---|
| Normal behavior profiles | MISSING | No baseline profile per agent |
| Session baselines | MISSING | No per-session baseline |
| Behavioral drift | MISSING | No drift detection |
| Action-sequence anomaly | PARTIAL | sensitive_sequences in risk engine |
| Unusual tool selection | PARTIAL | unusual_tool_combination |
| Unusual target selection | MISSING | No target-selection anomaly |
| Unusual action velocity | PARTIAL | abnormal_action_rate |
| Unusual privilege escalation | PARTIAL | unusual_escalation |
| Unusual data access | MISSING | No data-access anomaly |
| Unexpected chaining | MISSING | No chaining anomaly |
| Looping behavior | MISSING | No loop detection |
| Recursive behavior | MISSING | No recursion detection |
| Runaway behavior | MISSING | No runaway detection |
| Autonomous escalation detection | PARTIAL | suspicious_child_creation |
| Policy drift detection | MISSING | No policy-drift detection |
| Intent/action mismatch | MISSING | No intent/action divergence check |

### 06 — Prompt Injection Defense
| Capability | Status | Notes |
|---|---|---|
| Direct prompt injection detection | IMPLEMENTED | PROMPT_INJECTION_PATTERNS in IntentEvaluatorService |
| Indirect prompt injection detection | PARTIAL | retrieved-content inspection limited |
| Malicious retrieved content | PARTIAL | context inspection exists; no full malicious-content pipeline |
| Malicious documents | MISSING | No document parsing/analysis |
| Poisoned tools | PARTIAL | tool_security.py exists; no poisoning detection |
| Poisoned MCP servers | MISSING | No MCP security layer |
| Tool-description injection | MISSING | No tool-description sanitization |
| Instruction hierarchy attacks | PARTIAL | trust separation exists; no hierarchy enforcement |
| Hidden instructions | PARTIAL | zero-width detection; no full hidden-instruction detection |
| Encoded instructions | PARTIAL | base64 detection; limited encoding support |
| Context poisoning | MISSING | No cross-turn context poisoning defense |
| Memory poisoning | MISSING | No memory poisoning defense |
| Cross-session poisoning | MISSING | No cross-session isolation for context |
| Agent-to-agent instruction attacks | MISSING | No agent-to-agent instruction validation |

### 07 — Tool Security
| Capability | Status | Notes |
|---|---|---|
| Tool inventory | PARTIAL | tool name tracked; no central tool registry |
| Tool trust score | MISSING | No trust scoring per tool |
| Tool provenance | MISSING | No provenance chain |
| Tool permissions | PARTIAL | tool argument validation; no tool-level permission model |
| Tool signature | MISSING | No tool signature verification |
| Tool version | MISSING | No tool version tracking |
| Tool reputation | MISSING | No reputation system |
| Tool dependency graph | MISSING | No tool dependency mapping |
| Tool sandboxing | MISSING | No sandbox enforcement |
| Tool allowlist | PARTIAL | policy patterns act as allowlist; no explicit allowlist |
| Tool denylist | PARTIAL | blocked_patterns act as denylist |
| Dynamic authorization | PARTIAL | per-request evaluation exists |
| Tool anomaly detection | MISSING | No tool anomaly detection |
| Tool rollback | MISSING | No tool rollback support |
| Malicious tool detection | PARTIAL | suspicious tool call metrics; no detection engine |

### 08 — MCP Security
| Capability | Status | Notes |
|---|---|---|
| Server registry | MISSING | No MCP server registry |
| Server identity | MISSING | No MCP identity model |
| Server provenance | MISSING | No provenance tracking |
| Tool inventory | MISSING | No MCP tool inventory |
| Resource inventory | MISSING | No MCP resource inventory |
| Prompt inventory | MISSING | No MCP prompt inventory |
| Trust levels | MISSING | No MCP trust model |
| Scoped credentials | MISSING | No scoped credential model for MCP |
| Authorization | MISSING | No MCP authorization |
| Tool-level policy | MISSING | No MCP tool policy |
| Argument validation | PARTIAL | generic argument validation only |
| Output validation | MISSING | No MCP output validation |
| Data classification | MISSING | No MCP data classification |
| Egress control | MISSING | No MCP egress policy |
| Runtime containment | MISSING | No MCP runtime containment |
| MCP session replay | MISSING | No MCP replay |
| MCP evidence | MISSING | No MCP evidence capture |
| MCP incident reconstruction | MISSING | No MCP incident reconstruction |
| MCP recovery hooks | MISSING | No MCP recovery hooks |
| MCP policy simulation | MISSING | No MCP policy simulation |

### 09 — Agent-to-Agent Security
| Capability | Status | Notes |
|---|---|---|
| Delegation | IMPLEMENTED | Authority grants between agents |
| Multi-agent authority | IMPLEMENTED | authority lineage |
| Sub-agent creation | PARTIAL | create_agent action tracked; no creation policy |
| Identity inheritance | PARTIAL | parent_agent_id; no automatic token inheritance |
| Authority attenuation | PARTIAL | scope check exists; no attenuation rules |
| Agent communication | MISSING | No agent-to-agent message policy |
| Message authorization | MISSING | No message authz |
| Agent trust | PARTIAL | TrustLevel enum; no trust scoring |
| Agent reputation | MISSING | No reputation system |
| Lateral movement | PARTING | grant delegation tracked; no lateral-movement detection |
| Confused deputy | PARTIAL | deputy concept partially modeled; no explicit confused-deputy prevention |
| Malicious sub-agent | MISSING | No sub-agent anomaly detection |
| Compromised sub-agent | PARTIAL | containment cascades to children |
| Cascading failure | PARTIAL | cascade containment exists; no cascading failure detection |
| Cross-agent containment | IMPLEMENTED | CascadeContainmentService |
| Coordinated recovery | PARTIAL | recovery plan supports multiple actions; no coordinated multi-agent recovery protocol |

### 10 — Containment
| Capability | Status | Notes |
|---|---|---|
| Action deny | IMPLEMENTED | authorization denies |
| Session freeze | PARTIAL | session status changes; no freeze enforcement |
| Session quarantine | PARTIAL | session status exists; no quarantine enforcement |
| Agent freeze | PARTIAL | AgentStatus.QUARANTINED; no freeze semantics |
| Agent revoke | PARTIAL | status change only; no revoke lifecycle |
| Token revoke | PARTIAL | nonce consumed; no revocation list |
| Credential revoke | MISSING | No credential revocation workflow |
| Tool isolation | MISSING | No tool isolation |
| Network isolation | MISSING | No network isolation hooks |
| Workload quarantine | PARTIAL | agent quarantine; no workload quarantine |
| Process termination | MISSING | No process termination control |
| Environment isolation | MISSING | No environment isolation |
| Tenant isolation | IMPLEMENTED | tenant scoping |
| Cascading containment | IMPLEMENTED | CascadeContainmentService |
| Emergency global containment | MISSING | No global emergency mode |
| Containment policies | PARTIAL | mode enum exists; no policy-driven containment |
| Containment playbooks | MISSING | No playbook engine |
| Automatic triggers | PARTIAL | cascade on compromise; no trigger rules |
| Human triggers | PARTIAL | manual containment via API; no approval-gated trigger |
| Timed quarantine | MISSING | No timed quarantine/recovery |
| Staged containment | MISSING | No staged containment |
| Containment verification | PARTIAL | containment events logged; no verification checks |
| Containment evidence | IMPLEMENTED | ContainmentEvent entity |
| Containment replay | MISSING | No containment replay |
| Containment effectiveness | MISSING | No effectiveness measurement |

### 11 — Change Attribution
| Capability | Status | Notes |
|---|---|---|
| Attribute to agent | IMPLEMENTED | agent_id on ProtectedAction |
| Attribute to session | IMPLEMENTED | agent_session_id linkage |
| Attribute to intent | IMPLEMENTED | AgentActionDAG |
| Attribute to action | IMPLEMENTED | action_type |
| Attribute to token | PARTIAL | authority_grant_id; execution token not always linked |
| Attribute to tool | IMPLEMENTED | tool field |
| Attribute to user | PARTIAL | actor_user_id; often None |
| Attribute to service | PARTIAL | service_id in DTO |
| Attribute to workflow | PARTIAL | workflow_id in ProtectedAction |
| Attribute to transaction | PARTIAL | no transaction ID |
| Attribute to timestamp | IMPLEMENTED | created_at, executed_at |
| Attribute to environment | PARTIAL | environment field absent |
| Detect shared changes | MISSING | No shared-change detection |
| Detect mixed-origin changes | PARTIAL | causal graph separates direct/dependent/unrelated |
| Detect human-after-agent | MISSING | No temporal ordering analysis |
| Detect agent-after-human | MISSING | No temporal ordering analysis |
| Detect competing agents | MISSING | No competing-agent detection |
| Detect concurrent writers | MISSING | No concurrency detection beyond adapter-level |
| Detect ambiguous provenance | MISSING | No ambiguity detection |

### 12 — State Capture
| Capability | Status | Notes |
|---|---|---|
| Bytes | PARTIAL | before_state_snapshot stores dict; no exact bytes |
| Text | PARTIAL | dict representation |
| Binary | MISSING | No binary-safe state capture |
| Encoding | MISSING | No encoding metadata |
| BOM | MISSING | No BOM tracking |
| LF/CRLF | MISSING | No line-ending preservation |
| Metadata | PARTIAL | limited metadata in snapshot |
| Permissions | MISSING | No permission capture |
| Ownership | MISSING | No ownership capture |
| ACLs | MISSING | No ACL capture |
| DB row state | PARTIAL | database adapter captures row state |
| Table metadata | PARTIAL | schema captured in database adapter |
| Configuration | IMPLEMENTED | config adapters capture config state |
| Git tree | PARTIAL | GitRepositoryAdapter captures tree |
| Commit ancestry | PARTIAL | Git adapter uses commit history |
| Cloud resource state | MISSING | No cloud state capture |
| API state | MISSING | No API state capture |
| Object state | PARTIAL | generic object state via dict |
| Dependency state | PARTIAL | causal graph tracks dependencies |
| Schema state | PARTIAL | database schema captured |
| Version identifiers | PARTIAL | plan_version, policy_version exist |
| Hashes | PARTIAL | evidence hashes; limited state hashing |
| Merkle proofs | MISSING | No Merkle proof chain |

### 13 — Recovery Engine
| Capability | Status | Notes |
|---|---|---|
| Filesystem recovery | IMPLEMENTED | FilesystemRecoveryAdapter production-validated |
| Git recovery | IMPLEMENTED | GitRepositoryAdapter production-validated |
| Database recovery | IMPLEMENTED | DatabaseRecoveryAdapter production-validated |
| Configuration recovery | IMPLEMENTED | ConfigRecoveryAdapter production-validated |
| Cloud recovery | MISSING | No cloud adapters |
| Kubernetes recovery | MISSING | No Kubernetes adapters |
| Container recovery | MISSING | No container adapters |
| Object storage recovery | MISSING | No object storage adapters |
| Queue recovery | MISSING | No queue adapters |
| Cache recovery | MISSING | No cache adapters |
| Secrets metadata recovery | PARTIAL | no secret recovery; metadata only |
| Infrastructure recovery | MISSING | No infrastructure-as-code recovery |
| API objects recovery | MISSING | No API object recovery |
| SaaS objects recovery | MISSING | No SaaS recovery |
| Tickets/tasks recovery | MISSING | No ticketing recovery |
| Workflow state recovery | PARTIAL | workflow_id tracked; no workflow recovery |
| Financial state recovery | PARTIAL | payment adapters exist; no financial recovery |
| Email metadata recovery | MISSING | No email recovery |
| Permission changes recovery | PARTIAL | database adapter can recover permission rows |
| Identity changes recovery | MISSING | No identity recovery |
| Before-state capture | IMPLEMENTED | before_state_ref, before_state_snapshot |
| After-state capture | IMPLEMENTED | after_state_ref |
| Exact restoration | PARTIAL | adapters attempt exact restoration; no universal guarantee |
| Conflict detection | IMPLEMENTED | ConflictResult in adapters |
| Concurrency handling | PARTIAL | adapter-level locking; no distributed locking |
| Dry-run | IMPLEMENTED | simulate_plan, dry_run parameter |
| Preview | PARTIAL | simulation_result on plan |
| Rollback plan | IMPLEMENTED | RecoveryPlan with steps |
| Compensation | IMPLEMENTED | compensation_payload |
| Retry | PARTIAL | max_retries on DurableExecutionStep |
| Resume | PARTIAL | durable execution supports resume |
| Idempotency | IMPLEMENTED | idempotency_key on steps |
| Safe convergence | PARTIAL | partial_success handling; no convergence proof |
| Verification | IMPLEMENTED | ContinuousVerificationService |
| Failure classification | IMPLEMENTED | ExecutionState enum |

### 14 — Irreversible Action Handling
| Capability | Status | Notes |
|---|---|---|
| Reversible classification | IMPLEMENTED | Reversibility enum |
| Compensatable classification | IMPLEMENTED | Reversibility.CONDITIONALLY_REVERSIBLE |
| Partially compensatable | PARTIAL | partial_success state; no explicit partial compensatable class |
| Irreversible classification | IMPLEMENTED | Reversibility.IRREVERSIBLE |
| Unknown classification | IMPLEMENTED | Reversibility.UNKNOWN |
| Impact detection | PARTIAL | RollbackImpact exists; no automated impact detection |
| Evidence preservation | IMPLEMENTED | RecoveryEvidence entity |
| Compensation plan | IMPLEMENTED | compensation_payload on evidence |
| Human escalation | IMPLEMENTED | REQUIRES_MANUAL_ACTION state |
| Affected-party notification | MISSING | No notification hooks |
| Audit trail | IMPLEMENTED | JSONL audit log |
| Residual-risk calculation | PARTIAL | residual risk field on plan; no calculation engine |

### 15 — Recovery Planning
| Capability | Status | Notes |
|---|---|---|
| Dependency graph | PARTIAL | topological_order computed; no explicit graph model |
| Recovery ordering | IMPLEMENTED | reverse-topological order |
| Conflict analysis | IMPLEMENTED | ConflictResult |
| Blast-radius minimization | MISSING | No blast-radius minimization algorithm |
| Minimal-change recovery | PARTIAL | minimal-change is implicit goal |
| Maximal-safety recovery | PARTIAL | safety-first ordering |
| Alternate recovery plans | MISSING | No alternate plan generation |
| Plan comparison | MISSING | No plan comparison |
| Plan scoring | PARTIAL | plan_hash exists; no scoring model |
| Uncertainty representation | PARTIAL | ExecutionState.UNKNOWN_EXTERNAL_OUTCOME |
| Rollback boundary | MISSING | No rollback boundary definition |
| Compensation boundary | MISSING | No compensation boundary |
| Human approval gates | IMPLEMENTED | HITL approval queue |
| Recovery simulation | IMPLEMENTED | simulate_plan |
| Recovery preview | PARTIAL | simulation_result on plan |
| Recovery explanation | PARTIAL | compensation_summary exists |

### 16 — Recovery Verification
| Capability | Status | Notes |
|---|---|---|
| Exact hash verification | PARTIAL | hashes on evidence; no independent hash verification pass |
| Content comparison | PARTIAL | adapter-level verification |
| Structural comparison | PARTIAL | schema validation in database adapter |
| Schema validation | PARTIAL | database adapter checks schema |
| Database integrity | PARTIAL | foreign-key checks in database adapter |
| Foreign-key verification | PARTIAL | FK checks in database adapter |
| Invariant verification | MISSING | No invariant engine |
| Permission verification | PARTIAL | ownership checks in filesystem adapter |
| Dependency verification | PARTIAL | topological order verification |
| Service-health verification | MISSING | No service health checks |
| Application-level verification | MISSING | No application-level checks |
| Semantic verification | MISSING | No semantic verification |
| Cross-system consistency | MISSING | No cross-system consistency verification |
| Recovery completeness | PARTIAL | verification_passed flag on steps |
| Verification coverage | MISSING | No coverage metrics |
| Confidence scoring | PARTIAL | recovery_confidence_model exists |
| Residual risk | PARTIAL | residual risk field |

### 17 — Recovery Confidence
| Capability | Status | Notes |
|---|---|---|
| Evidence completeness | PARTIAL | evidence exists; no completeness metric |
| State certainty | PARTIAL | drift status gives certainty |
| Recovery coverage | MISSING | No coverage calculation |
| Dependency certainty | PARTIAL | dependency graph exists; no certainty metric |
| Conflict status | IMPLEMENTED | ConflictStatus enum |
| External side effects | PARTIAL | unknown_external_outcome state |
| Irreversible actions | IMPLEMENTED | Reversibility.IRREVERSIBLE |
| Verification coverage | MISSING | No verification coverage metric |
| Adapter reliability | PARTIAL | AdapterCapability enum |
| Execution certainty | PARTIAL | ExecutionState gives certainty |
| Confidence score | PARTIAL | confidence_score field on plan |
| Confidence band | MISSING | No confidence band |
| Explanation | PARTIAL | compensation_summary; no structured explanation |
| Unresolved uncertainty | PARTIAL | limitations field |
| Recommended human action | PARTIAL | requires_manual_action state |

### 18 — Incident Response
| Capability | Status | Notes |
|---|---|---|
| Detect | PARTIAL | incident created; no automatic detection rules |
| Declare | PARTIAL | incident entity exists; no declaration workflow |
| Contain | IMPLEMENTED | CascadeContainmentService |
| Investigate | PARTIAL | causal graph, timeline events |
| Reconstruct | IMPLEMENTED | ChangesetReconstructionService |
| Plan | IMPLEMENTED | RecoveryPlanningService |
| Recover | IMPLEMENTED | DistributedRecoveryOrchestrator |
| Verify | IMPLEMENTED | ContinuousVerificationService |
| Close | PARTIAL | IncidentStatus.RESOLVED; no closure workflow |
| Learn | MISSING | No lessons-learned capture |
| Severity | IMPLEMENTED | IncidentSeverity enum |
| Classification | PARTIAL | trigger field; no classification taxonomy |
| Timeline | IMPLEMENTED | IncidentTimelineEvent entity |
| Evidence bundle | PARTIAL | evidence linked to incident; no bundle export |
| Affected resources | IMPLEMENTED | affected_resources list |
| Affected tenants | IMPLEMENTED | tenant_id scoped |
| Root-cause hypotheses | MISSING | No hypothesis engine |
| Recovery plan | IMPLEMENTED | linked to incident |
| Recovery status | PARTIAL | rollback_state on incident |
| Residual risk | PARTIAL | residual risk field |
| Lessons learned | MISSING | No lessons-learned entity |
| Incident export | PARTIAL | compliance evidence export exists |

### 19 — Forensics
| Capability | Status | Notes |
|---|---|---|
| Event timeline | IMPLEMENTED | IncidentTimelineEvent |
| Action graph | PARTIAL | causal graph service |
| Causal graph | IMPLEMENTED | CausalGraphService |
| Dependency graph | PARTIAL | topological order; no explicit dependency graph entity |
| Token graph | MISSING | No token graph |
| Identity graph | PARTIAL | authority lineage |
| Tool graph | MISSING | No tool graph |
| Resource graph | MISSING | No resource graph |
| Mutation graph | PARTIAL | causal graph approximates mutation graph |
| Recovery graph | MISSING | No recovery graph |
| Incident replay | PARTIAL | simulation exists; no incident replay |
| Evidence chain | PARTIAL | evidence entities linked; no chain validation |
| Tamper detection | PARTIAL | JSONL audit with hash-chain idea; no implementation |
| Evidence signatures | PARTIAL | Ed25519 tokens; no evidence signing |
| Evidence export | PARTIAL | compliance export exists |
| Forensic snapshots | MISSING | No forensic snapshot |

### 20 — Agent Replay
| Capability | Status | Notes |
|---|---|---|
| Intent replay | PARTIAL | simulate endpoint; no replay API |
| Action replay | PARTIAL | simulation engine |
| Tool call replay | PARTIAL | simulation only |
| Policy decision replay | PARTIAL | policy evaluation re-runnable |
| State transition replay | PARTIAL | recovery simulation |
| Failure replay | PARTIAL | recovery simulation supports failure modes |
| Recovery plan replay | PARTIAL | simulate_plan |
| Verification replay | PARTIAL | re-verification possible |
| Default to simulation | IMPLEMENTED | simulation-first design |
| No accidental real execution | PARTIAL | simulation mode exists; no hard separation in all paths |

### 21 — Digital Twin / Simulation
| Capability | Status | Notes |
|---|---|---|
| Simulated agent | PARTIAL | mock adapter uses simulated actions |
| Simulated tools | PARTIAL | MockRecoveryAdapter simulates tools |
| Simulated resources | PARTIAL | mock state in tests |
| Simulated filesystem | PARTIAL | test fixtures use temp dirs |
| Simulated Git | PARTIAL | test fixtures |
| Simulated DB | PARTIAL | SQLite in-memory |
| Simulated APIs | PARTIAL | mock adapters |
| Simulated cloud | MISSING | No cloud simulation |
| Simulated failures | PARTIAL | recovery simulation includes failures |
| Simulated conflicts | PARTIAL | conflict detection tested |
| Simulated compromise | PARTIAL | demo scripts exist |
| Simulated recovery | IMPLEMENTED | RecoverySimulationEngine |
| Simulated containment | PARTIAL | cascade containment tests |
| Expected vs Observed vs Recovered | PARTIAL | comparison in verification; no unified twin view |

### 22 — Agent Chaos Engineering
| Capability | Status | Notes |
|---|---|---|
| Random action failure | MISSING | No chaos injector |
| Delayed response | MISSING | No delay injection |
| Network failure | MISSING | No network chaos |
| Permission failure | PARTIAL | test fixtures simulate permission errors |
| Stale state | PARTIAL | drift detection tests |
| Concurrent modification | PARTIAL | conflict tests |
| Corrupted output | MISSING | No corruption injection |
| Invalid tool response | MISSING | No invalid-response injection |
| Malicious tool | PARTIAL | malicious tool simulation in tests |
| Prompt injection | PARTIAL | injection patterns tested |
| Token replay | IMPLEMENTED | replay tests exist |
| Authority revocation | PARTIAL | cascade revocation tested |
| Crash mid-recovery | PARTIAL | crash recovery tests in recovery_lab |
| Database conflict | PARTIAL | conflict detection in database adapter |
| Filesystem conflict | PARTIAL | filesystem adapter conflict tests |
| Service outage | PARTIAL | Redis outage fail-closed tests |
| Resilience measurements | MISSING | No resilience scoring |

### 23 — Continuous Checkpointing
| Capability | Status | Notes |
|---|---|---|
| Action checkpoints | PARTIAL | ProtectedAction journal |
| State checkpoints | PARTIAL | StateCheckpoint entity |
| Session checkpoints | PARTIAL | AgentSession state |
| Transaction checkpoints | MISSING | No transaction checkpoint |
| Recovery checkpoints | PARTIAL | DurableExecutionStep |
| Incremental snapshots | MISSING | No incremental snapshot |
| Checkpoint retention | MISSING | No retention policy |
| Checkpoint compression | MISSING | No compression |
| Checkpoint verification | PARTIAL | verification service |
| Checkpoint GC | MISSING | No garbage collection |

### 24 — Universal Action Model
| Capability | Status | Notes |
|---|---|---|
| Canonical read | PARTIAL | action_type string; no canonical model |
| Canonical write | PARTIAL | action_type string |
| Canonical create | PARTIAL | action_type string |
| Canonical update | PARTIAL | action_type string |
| Canonical delete | PARTIAL | action_type string |
| Canonical execute | PARTIAL | action_type string |
| Canonical rename | PARTIAL | filesystem adapter supports rename |
| Canonical move | PARTIAL | filesystem adapter |
| Canonical permission change | PARTIAL | database adapter can recover permission rows |
| Canonical credential change | MISSING | No credential change model |
| Canonical API call | PARTIAL | HTTP_REST adapter type exists |
| Canonical DB transaction | PARTIAL | database adapter |
| Canonical infrastructure change | MISSING | No infrastructure action model |
| Canonical network operation | MISSING | No network action model |
| Canonical financial operation | PARTIAL | payment provider interface |
| Canonical communication | MISSING | No communication action model |
| Canonical agent delegation | IMPLEMENTED | authority grants |
| Adapter translation | PARTIAL | adapters translate to compensation actions |

### 25 — Resource Graph
| Capability | Status | Notes |
|---|---|---|
| Graph of agents | PARTIAL | agent repository; no graph queries |
| Graph of sessions | PARTIAL | session repository |
| Graph of users | PARTIAL | user repository |
| Graph of tokens | PARTIAL | execution token repository |
| Graph of tools | MISSING | No tool graph |
| Graph of resources | MISSING | No resource graph |
| Graph of files | PARTIAL | filesystem adapter |
| Graph of repositories | PARTIAL | Git adapter |
| Graph of databases | PARTIAL | database adapter |
| Graph of cloud objects | MISSING | No cloud graph |
| Graph of APIs | MISSING | No API graph |
| Graph of services | PARTIAL | service_id field |
| Graph of incidents | PARTIAL | incident repository |
| Graph of recovery plans | PARTIAL | plan repository |
| Graph queries | MISSING | No graph query API |

### 26 — Data Security
| Capability | Status | Notes |
|---|---|---|
| Sensitive-data detection | PARTIAL | policy engine has patterns; no data classification engine |
| PII protection | PARTIAL | PII patterns in policy |
| Secrets protection | PARTIAL | no secret logging; no secret scanning |
| Credentials protection | PARTIAL | tokens and passwords hashed |
| Token protection | IMPLEMENTED | execution tokens signed |
| API key protection | IMPLEMENTED | API key hashing |
| Regulated data classification | MISSING | No classification engine |
| Data lineage | PARTIAL | causal graph provides lineage |
| Data egress monitoring | MISSING | No egress monitoring |
| Tool-output classification | MISSING | No output classification |
| Agent data access policies | PARTIAL | resource field; no data access policy |
| Masking | MISSING | No masking |
| Redaction | MISSING | No redaction |
| Evidence privacy | PARTIAL | tool arguments not logged |
| Tenant-specific retention | MISSING | No retention policy |

### 27 — Exfiltration Control
| Capability | Status | Notes |
|---|---|---|
| Unusual outbound detection | MISSING | No outbound monitoring |
| Unusual volume detection | MISSING | No volume anomaly |
| Sensitive-data egress | MISSING | No sensitive-data egress detection |
| Unexpected domains | MISSING | No domain allowlist |
| Unauthorized uploads | MISSING | No upload control |
| Suspicious API calls | PARTIAL | unusual tool combination |
| Credential leakage | PARTIAL | no secret logging; no leakage detection |
| Encoded payloads | PARTIAL | base64 detection |
| Secret extraction | PARTIAL | prompt injection detection includes reveal prompt |

### 28 — Network Control
| Capability | Status | Notes |
|---|---|---|
| Destination allowlists | MISSING | No network allowlist |
| Destination policies | MISSING | No destination policy |
| Network risk | MISSING | No network risk scoring |
| DNS monitoring | MISSING | No DNS hooks |
| Egress rules | MISSING | No egress rules |
| Service-to-service policy | MISSING | No service mesh policy |
| Network containment | MISSING | No network containment |
| Connection provenance | MISSING | No connection provenance |
| Anomaly detection | PARTIAL | cross_boundary signal |
| Emergency network isolation | MISSING | No emergency isolation |

### 29 — Cloud Control
| Capability | Status | Notes |
|---|---|---|
| AWS adapter | MISSING | No AWS adapter |
| Azure adapter | MISSING | No Azure adapter |
| GCP adapter | MISSING | No GCP adapter |
| IAM control | PARTIAL | no cloud IAM adapter |
| Compute control | MISSING | No compute adapter |
| Storage control | MISSING | No storage adapter |
| Database control | MISSING | No cloud DB adapter |
| Networking control | MISSING | No networking adapter |
| Secrets control | PARTIAL | no cloud secrets adapter |
| Queue control | MISSING | No queue adapter |
| Functions control | MISSING | No function adapter |
| Kubernetes control | MISSING | No K8s adapter |
| IaC control | MISSING | No IaC adapter |
| Least authority | PARTIAL | least authority principle documented; not enforced in cloud adapters |

### 30 — Kubernetes
| Capability | Status | Notes |
|---|---|---|
| Namespace policies | MISSING | No K8s namespace policies |
| Workload identity | MISSING | No K8s workload identity |
| Pod actions | MISSING | No pod action model |
| Exec control | MISSING | No exec control |
| Secret access | MISSING | No secret access control |
| Network policy hooks | MISSING | No network policy integration |
| Deployment mutation control | MISSING | No deployment control |
| Admission integration | MISSING | No admission webhook |
| Quarantine | MISSING | No K8s quarantine |
| Workload rollback | MISSING | No K8s rollback |
| State capture | MISSING | No K8s state capture |
| Verification | MISSING | No K8s verification |

### 31 — Database Security & Recovery
| Capability | Status | Notes |
|---|---|---|
| Row-level attribution | PARTIAL | database adapter captures rows |
| Transaction provenance | MISSING | No transaction provenance |
| Schema change tracking | PARTIAL | schema captured in adapter |
| Migration detection | MISSING | No migration detection |
| Destructive query detection | IMPLEMENTED | sqlglot destructive SQL checks |
| Parameter enforcement | IMPLEMENTED | parameterized queries |
| SQL injection defense | IMPLEMENTED | whitelist + parameterization |
| Transaction boundaries | PARTIAL | transaction context passed |
| Concurrent-write handling | PARTIAL | conflict detection |
| Before-image | IMPLEMENTED | before_state_snapshot |
| After-image | IMPIAL | after_state_snapshot |
| Dependency-aware recovery | PARTIAL | topological order |
| Constraint verification | PARTIAL | foreign-key checks |
| Index verification | MISSING | No index verification |
| Trigger awareness | MISSING | No trigger awareness |

### 32 — Git / Code Recovery
| Capability | Status | Notes |
|---|---|---|
| Commit provenance | PARTIAL | Git adapter uses commits |
| Branch provenance | PARTIAL | branch parameter in Git adapter |
| Agent commit detection | PARTIAL | agent_id tracked in actions |
| Agent push detection | PARTIAL | push actions tracked |
| PR attribution | MISSING | No PR model |
| Diff classification | PARTIAL | diff computed in adapter |
| Human-change preservation | IMPLEMENTED | conflict detection preserves human changes |
| Merge conflict recovery | PARTIAL | conflict detection; no merge recovery |
| Partial rollback | PARTIAL | file-level rollback |
| Branch quarantine | MISSING | No branch quarantine |
| Secret scan after recovery | MISSING | No secret scan |
| Dependency scan | MISSING | No dependency scan |
| Build verification | MISSING | No build verification |
| Test verification | MISSING | No test verification |

### 33 — Filesystem
| Capability | Status | Notes |
|---|---|---|
| Exact byte capture | PARTIAL | content captured; no exact byte preservation guarantee |
| Metadata | PARTIAL | metadata preservation flag |
| Permission state | PARTIAL | preserve_metadata flag |
| Ownership | PARTIAL | metadata preservation |
| Symlink awareness | MISSING | No symlink handling |
| Hardlink awareness | MISSING | No hardlink handling |
| Atomic mutation | PARTIAL | atomic file ops used |
| Rename | IMPLEMENTED | rename recovery supported |
| Move | PARTIAL | treated as rename + path change |
| Delete | IMPLEMENTED | delete recovery |
| Recreate | IMPLEMENTED | create recovery |
| Binary files | PARTIAL | binary content handled as bytes |
| Large files | PARTIAL | max_file_size_bytes limit |
| Conflict detection | IMPLEMENTED | conflict detection |
| Concurrent modification | PARTIAL | drift detection |
| Recovery verification | PARTIAL | adapter verification |

### 34 — API Security
| Capability | Status | Notes |
|---|---|---|
| API action policies | PARTIAL | general policy engine |
| Schema validation | PARTIAL | Pydantic validation |
| Argument validation | IMPLEMENTED | ToolArgumentValidator |
| Response validation | PARTIAL | response validation limited |
| Rate controls | IMPLEMENTED | RateLimitMiddleware |
| Idempotency | PARTIAL | idempotency_key on recovery steps |
| Replay prevention | IMPLEMENTED | execution token nonce |
| Destination policy | MISSING | No destination allowlist |
| Data classification | MISSING | No data classification |
| Side-effect classification | PARTIAL | Reversibility enum |
| Compensating operations | IMPLEMENTED | compensation_payload |
| Response evidence | PARTIAL | after_state_ref |

### 35 — Financial / High-Impact Action Control
| Capability | Status | Notes |
|---|---|---|
| Transaction classification | PARTIAL | financial transfer patterns detected |
| Amount thresholds | MISSING | No amount threshold enforcement |
| Recipient allowlists | MISSING | No recipient allowlist |
| Approval thresholds | PARTIAL | HITL exists; no threshold-based approval |
| Velocity thresholds | MISSING | No velocity limits |
| Anomaly detection | PARTIAL | risk engine signals |
| Irreversible-action warnings | PARTIAL | reversibility classification |
| Dual control | MISSING | No dual control |
| Human approval | IMPLEMENTED | HITL queue |
| Evidence | IMPLEMENTED | RecoveryEvidence |
| Compensation hooks | PARTIAL | compensation_payload |

### 36 — Human-in-the-Loop
| Capability | Status | Notes |
|---|---|---|
| Approval gates | IMPLEMENTED | HITL approval queue |
| Step-up authentication | MISSING | No step-up MFA for approvals |
| Multi-person approval | PARTIAL | approval_threshold exists |
| Approval expiration | PARTIAL | no TTL on approvals |
| Approval scope | PARTIAL | scope on approval request |
| Approval provenance | PARTIAL | approved_by tracked |
| Emergency approval | PARTIAL | no emergency approval path |
| Rejection reason | MISSING | No rejection reason capture |
| Escalation | PARTIAL | escalation via HITL |
| Delegated approval | MISSING | No delegated approval |
| Approval auditing | PARTIAL | approval events logged |

### 37 — Policy as Code
| Capability | Status | Notes |
|---|---|---|
| Policy language | PARTIAL | YAML configuration |
| Policy schema | MISSING | No formal schema |
| Policy compiler | MISSING | No compiler |
| Policy validator | MISSING | No validator |
| Policy linter | MISSING | No linter |
| Policy test framework | MISSING | No test framework |
| Policy simulator | MISSING | No simulator |
| Policy versioning | PARTIAL | policy_version field |
| Policy diff | MISSING | No diff |
| Policy rollback | MISSING | No rollback |
| Policy deployment | MISSING | No deployment workflow |
| Policy approval workflow | MISSING | No approval workflow for policies |

### 38 — Policy Explainability
| Capability | Status | Notes |
|---|---|---|
| What was requested | PARTIAL | AgentActionDAG captures intent |
| Who requested it | PARTIAL | agent_id, actor_user_id |
| Applicable policies | PARTIAL | policy rules matched |
| Conditions evaluated | PARTIAL | conditions on grants |
| Risk factors | IMPLEMENTED | RiskEngine signals |
| Final decision | IMPLEMENTED | AuthorizationDecision |
| Authority used | PARTIAL | authority_grant_id |
| Reason | IMPLEMENTED | decision_reason |
| Expiration | PARTIAL | expires_at on grants |

### 39 — Observability
| Capability | Status | Notes |
|---|---|---|
| Metrics | PARTIAL | SecurityMetrics in-memory |
| Structured logs | PARTIAL | JSONL audit log |
| Traces | MISSING | No OpenTelemetry traces |
| OpenTelemetry | MISSING | No OTLP integration |
| Action telemetry | PARTIAL | metrics increment |
| Policy telemetry | PARTIAL | policy_decisions metric |
| Recovery telemetry | PARTIAL | recovery_adapter_calls metric |
| Containment telemetry | PARTIAL | containment_cascade_depth metric |
| Verification telemetry | PARTIAL | verification metrics missing |
| Performance telemetry | MISSING | No performance telemetry |

### 40 — SRE / Reliability
| Capability | Status | Notes |
|---|---|---|
| Health checks | IMPLEMENTED | /health endpoint |
| Readiness | IMPLEMENTED | /ready endpoint |
| Liveness | IMPLEMENTED | /health endpoint |
| Dependency health | PARTIAL | /ready checks DB + Redis |
| Queue monitoring | MISSING | No queue monitoring |
| Timeout controls | PARTIAL | SDK timeout=5s |
| Retry policy | PARTIAL | max_retries on steps |
| Circuit breakers | MISSING | No circuit breakers |
| Backpressure | MISSING | No backpressure |
| Graceful degradation | PARTIAL | fail-closed on Redis |
| Recovery after crash | PARTIAL | durable execution supports resume |
| Recovery after machine crash | PARTIAL | durable state in DB |
| Durable state | IMPLEMENTED | PostgreSQL persistence |
| Failover | MISSING | No failover |
| Disaster recovery | MISSING | No DR procedure |

### 41 — Distributed Recovery
| Capability | Status | Notes |
|---|---|---|
| Durable orchestration | IMPLEMENTED | DistributedRecoveryOrchestrator |
| Distributed locks | PARTIAL | in-process locks only |
| Concurrency | PARTIAL | thread-level locking |
| Leader election | MISSING | No leader election |
| Plan recovery | PARTIAL | durable steps |
| Resume | IMPLEMENTED | resume from durable steps |
| Step deduplication | PARTIAL | idempotency_key |
| Partial failures | IMPLEMENTED | partial_success state |
| Network partitions | MISSING | No partition handling |
| Execution leases | MISSING | No leases |
| Fencing | MISSING | No fencing |
| Safe convergence | PARTIAL | idempotency + partial success |

### 42 — Multi-Tenancy
| Capability | Status | Notes |
|---|---|---|
| Tenant isolation | IMPLEMENTED | tenant_id scoping |
| Tenant-specific policies | PARTIAL | tenant_id in policy context |
| Tenant-specific evidence | IMPLEMENTED | tenant-scoped repositories |
| Tenant-specific encryption | MISSING | No tenant-specific encryption keys |
| Tenant-specific recovery | IMPLEMENTED | tenant-scoped recovery |
| Tenant quotas | MISSING | No quota enforcement |
| Tenant rate limits | MISSING | No tenant rate limits |
| Tenant configuration | PARTIAL | settings exist; no tenant config |
| Tenant audit | PARTIAL | audit log includes tenant_id |
| Tenant export | PARTIAL | compliance export |
| Tenant data retention | MISSING | No retention policy |
| Cross-tenant attack prevention | IMPLEMENTED | cross-tenant access denied |

### 43 — Enterprise Security
| Capability | Status | Notes |
|---|---|---|
| SSO | PARTIAL | mock adapters only |
| OIDC | PARTIAL | mock adapter |
| SAML | PARTIAL | mock adapter |
| SCIM | MISSING | No SCIM |
| RBAC | PARTIAL | role-based approval |
| ABAC | PARTIAL | attribute-based conditions |
| MFA integration | PARTIAL | TOTP MFA; no enterprise MFA |
| Session controls | PARTIAL | session management |
| Audit exports | PARTIAL | compliance evidence export |
| Enterprise key management | PARTIAL | KMS/HSM interfaces |
| KMS | PARTIAL | interface only |
| HSM | PARTIAL | interface only |
| Certificate rotation | MISSING | No cert rotation |
| Secret rotation | MISSING | No secret rotation |
| Security headers | IMPLEMENTED | SecurityHeadersMiddleware |
| Secure configuration | PARTIAL | settings with validation |

### 44 — Compliance Evidence
| Capability | Status | Notes |
|---|---|---|
| Access review evidence | PARTIAL | audit log |
| Authorization evidence | PARTIAL | policy decision logged |
| Change attribution | IMPLEMENTED | ProtectedAction |
| Incident evidence | PARTIAL | incident entity |
| Recovery evidence | IMPLEMENTED | RecoveryEvidence |
| Verification evidence | PARTIAL | verification_passed flag |
| Retention | MISSING | No retention policy |
| Audit trails | IMPLEMENTED | JSONL audit log |
| Policy history | PARTIAL | policy_version field |
| Administrative activity | PARTIAL | admin actions logged |

### 45 — Dashboard
| Capability | Status | Notes |
|---|---|---|
| Agent fleet view | MISSING | No dashboard implementation |
| Active sessions | MISSING | No session dashboard |
| Authority view | MISSING | No authority dashboard |
| Current risk | MISSING | No risk dashboard |
| Blocked actions | MISSING | No blocked-action view |
| Incidents | MISSING | No incident dashboard |
| Containment | MISSING | No containment dashboard |
| Recovery | MISSING | No recovery dashboard |
| Verification | MISSING | No verification dashboard |
| Evidence | MISSING | No evidence viewer |
| Trends | MISSING | No trend analysis |
| Attack patterns | MISSING | No attack pattern view |
| Resilience score | MISSING | No resilience scoring |
| Recovery confidence | PARTIAL | confidence score on plan |

### 46 — Incident Timeline UI
| Capability | Status | Notes |
|---|---|---|
| Timeline visualization | MISSING | No UI |
| Filter by agent | MISSING | No UI |
| Filter by session | MISSING | No UI |
| Filter by tenant | MISSING | No UI |
| Filter by resource | MISSING | No UI |
| Filter by tool | MISSING | No UI |
| Filter by incident | MISSING | No UI |
| Filter by time | MISSING | No UI |

### 47 — Recovery Workbench
| Capability | Status | Notes |
|---|---|---|
| Plan viewer | MISSING | No workbench UI |
| Dependency graph | MISSING | No graph visualization |
| Dry run | IMPLEMENTED | simulate_plan |
| Preview | PARTIAL | simulation_result |
| Approval | IMPLEMENTED | HITL queue |
| Execution | IMPLEMENTED | orchestrator |
| Pause | PARTIAL | stop condition |
| Resume | IMPLEMENTED | durable execution |
| Retry | PARTIAL | max_retries |
| Verify | IMPLEMENTED | verification service |
| Confidence | PARTIAL | confidence_score |
| Residual-risk view | PARTIAL | residual risk field |

### 48 — Security Research Mode
| Capability | Status | Notes |
|---|---|---|
| Fuzzing | PARTIAL | adversarial tests exist |
| Mutation testing | PARTIAL | property-based tests |
| Attack simulation | PARTIAL | recovery simulation |
| Malicious tool simulation | PARTIAL | mock malicious tools |
| Prompt injection simulation | PARTIAL | injection pattern tests |
| Replay | PARTIAL | simulation replay |
| Policy abuse testing | PARTIAL | adversarial policy tests |
| Token abuse testing | IMPLEMENTED | replay tests |
| Containment tests | IMPLEMENTED | cascade containment tests |
| Recovery fault injection | PARTIAL | crash recovery tests |

### 49 — Adversarial Testing
| Capability | Status | Notes |
|---|---|---|
| Authorization bypass | PARTIAL | adversarial tests include bypass |
| Token replay | IMPLEMENTED | replay protection tests |
| Tenant escape | PARTIAL | tenant isolation tests |
| Confused deputy | PARTIAL | confused deputy tests |
| Race conditions | PARTIAL | concurrency tests |
| TOCTOU | PARTIAL | TOCTOU tests |
| Partial failures | PARTIAL | failure injection tests |
| Forged evidence | PARTIAL | evidence tampering tests |
| Altered snapshots | PARTIAL | snapshot tampering tests |
| Recovery spoofing | PARTIAL | spoofing tests |
| False success | PARTIAL | false-success tests |
| Malicious tool | PARTIAL | malicious tool tests |
| Malicious agent | PARTIAL | malicious agent tests |
| Malicious user | PARTIAL | malicious user tests |
| Compromised credentials | PARTIAL | credential compromise tests |

### 50 — Formal / Property-Based Safety
| Capability | Status | Notes |
|---|---|---|
| Unauthorized mutation denied | PARTIAL | default deny |
| Revoked authority denied | PARTIAL | authority check |
| Tenant A cannot access tenant B evidence | IMPLEMENTED | tenant isolation |
| Recovery cannot overwrite human changes | IMPLEMENTED | conflict detection |
| Verification failure cannot produce RECOVERED | IMPLEMENTED | verification_passed required |
| Immutable evidence | PARTIAL | evidence entities frozen |
| Recovery plans durable across restart | IMPLEMENTED | durable execution |
| Token replay denied | IMPLEMENTED | nonce consumption |

### 51 — Performance
| Capability | Status | Notes |
|---|---|---|
| Authorization latency benchmark | MISSING | No benchmark |
| Token verification benchmark | MISSING | No benchmark |
| Action logging benchmark | MISSING | No benchmark |
| Evidence persistence benchmark | MISSING | No benchmark |
| Graph operations benchmark | MISSING | No benchmark |
| Recovery planning benchmark | MISSING | No benchmark |
| Recovery execution benchmark | MISSING | No benchmark |
| Verification benchmark | MISSING | No benchmark |
| Concurrent sessions benchmark | MISSING | No benchmark |
| Tenants benchmark | MISSING | No benchmark |
| Agents benchmark | MISSING | No benchmark |
| Actions benchmark | MISSING | No benchmark |
| Large datasets benchmark | MISSING | No benchmark |
| P50/P95/P99 measurement | MISSING | No measurement |
| Throughput measurement | MISSING | No measurement |
| CPU measurement | MISSING | No measurement |
| Memory measurement | MISSING | No measurement |
| I/O measurement | MISSING | No measurement |
| Storage growth | MISSING | No measurement |

### 52 — Scale
| Capability | Status | Notes |
|---|---|---|
| 1,000 actions | MISSING | No scale test |
| 5,000 actions | MISSING | No scale test |
| 10,000 actions | MISSING | No scale test |
| 100,000 actions | MISSING | No scale test |
| 1,000,000 actions | MISSING | No scale test |
| Concurrent agents | PARTIAL | unit tests with multiple agents |
| Concurrent tenants | PARTIAL | tenant isolation tests |
| Concurrent incidents | PARTIAL | incident tests |
| Concurrent recovery plans | PARTIAL | recovery lab tests |

### 53 — Cost Optimization
| Capability | Status | Notes |
|---|---|---|
| Snapshot storage optimization | MISSING | No optimization |
| Event storage optimization | MISSING | No optimization |
| Graph storage optimization | MISSING | No optimization |
| Log volume optimization | MISSING | No optimization |
| Serialization optimization | MISSING | No optimization |
| Compression | MISSING | No compression |
| Indexing | PARTIAL | SQLAlchemy indexes |
| Query optimization | PARTIAL | basic ORM queries |
| Background jobs | MISSING | No background job queue |
| Retry storm prevention | PARTIAL | max_retries limit |

### 54 — SDK
| Capability | Status | Notes |
|---|---|---|
| Typed clients | PARTIAL | IntentLockGuard typed |
| Safer defaults | PARTIAL | defaults set |
| Async support | MISSING | SDK is synchronous |
| Retries | MISSING | No SDK retries |
| Idempotency | PARTIAL | single-use enforced |
| Tracing | MISSING | No tracing |
| Structured errors | PARTIAL | SecurityError exception |
| Policy helpers | MISSING | No policy helpers |
| Recovery helpers | MISSING | No recovery helpers |
| Incident helpers | MISSING | No incident helpers |
| Simulation helpers | MISSIAL | simulation via API |
| Testing helpers | PARTIAL | test fixtures |

### 55 — CLI
| Capability | Status | Notes |
|---|---|---|
| Agent commands | MISSING | No CLI |
| Session commands | MISSING | No CLI |
| Authority commands | MISSING | No CLI |
| Policy commands | MISSING | No CLI |
| Action commands | MISSING | No CLI |
| Incident commands | MISSING | No CLI |
| Evidence commands | MISSING | No CLI |
| Recovery commands | MISSING | No CLI |
| Simulation commands | MISSING | No CLI |
| Benchmark commands | MISSING | No CLI |
| Diagnostic commands | MISSING | No CLI |

### 56 — Developer Experience
| Capability | Status | Notes |
|---|---|---|
| 5-minute installation | PARTIAL | setup documented |
| 10-minute demo | PARTIAL | demo scripts exist |
| 30-minute integration | PARTIAL | SDK + docs |
| Simple migration | MISSING | No migration guide |
| Excellent errors | PARTIAL | error handling exists |
| Excellent documentation | PARTIAL | docs exist |
| Examples | PARTIAL | examples/ directory |
| Templates | MISSING | No templates |
| Test harness | PARTIAL | pytest suite |
| Local dev stack | PARTIAL | docker-compose.yml |
| Troubleshooting | PARTIAL | docs/developer/ |
| Debugging | PARTIAL | correlation IDs |

### 57 — Documentation
| Capability | Status | Notes |
|---|---|---|
| Architecture docs | IMPLEMENTED | ARCHITECTURE.md |
| Security model | IMPLEMENTED | security-model.md |
| Threat model | IMPLEMENTED | THREAT_MODEL.md |
| Recovery model | IMPLEMENTED | recovery-model.md |
| Adapter guide | IMPLEMENTED | adapter-model.md |
| SDK guide | PARTIAL | sdk/README.md |
| Deployment guide | PARTIAL | README quickstart |
| Production checklist | PARTIAL | ARCHITECTURE.md checklist |
| Incident-response guide | PARTIAL | INCIDENT_RESPONSE.md |
| Integration guide | PARTIAL | EXAMPLES.md |
| Migration guide | MISSING | No migration guide |
| Limitations | IMPLEMENTED | Limitations section in README |
| Known risks | PARTIAL | risk register missing |
| Benchmark methodology | MISSING | No benchmark methodology |

### 58 — OpenTelemetry / Interoperability
| Capability | Status | Notes |
|---|---|---|
| OpenTelemetry | MISSING | No OTLP |
| Standard traces | MISSING | No traces |
| Standard metrics | PARTIAL | custom metrics |
| Standard logs | PARTIAL | JSONL logs |
| Standard resource metadata | PARTIAL | correlation IDs |
| Correlation IDs | IMPLEMENTED | CorrelationIdMiddleware |
| Trace propagation | MISSING | No trace context propagation |

### 59 — Agent Framework Integration
| Capability | Status | Notes |
|---|---|---|
| OpenAI agents | MISSING | No OpenAI integration |
| Anthropic agents | MISSING | No Anthropic integration |
| LangGraph | PARTIAL | LangChain adapter only |
| LangChain | IMPLEMENTED | IntentLockLangChainTool |
| CrewAI | MISSING | No CrewAI adapter |
| AutoGen | MISSING | No AutoGen adapter |
| OpenHands | MISSING | No OpenHands adapter |

### 60 — A2A / Agent Protocols
| Capability | Status | Notes |
|---|---|---|
| Identity | MISSING | No A2A identity |
| Authorization | MISSING | No A2A authz |
| Message policy | MISSING | No message policy |
| Trust | MISSING | No A2A trust |
| Provenance | PARTIAL | causal graph |
| Delegation | IMPLEMENTED | authority grants |
| Evidence | PARTIAL | evidence entities |
| Containment | PARTIAL | cascade containment |
| Incident reconstruction | PARTIAL | causal graph |
| Recovery hooks | PARTIAL | recovery adapters |

### 61 — Web / Browser Agents
| Capability | Status | Notes |
|---|---|---|
| Navigation control | MISSING | No browser control |
| Form submission control | MISSING | No form control |
| Download control | MISSING | No download control |
| Upload control | MISSING | No upload control |
| Browser credentials | MISSING | No browser credential control |
| External side effects | PARTIAL | reversibility classification |
| Sensitive destinations | MISSING | No destination policy |
| Payments | PARTIAL | payment provider interface |
| Destructive actions | PARTIAL | destructive SQL detection |
| Session isolation | PARTIAL | session entity |

### 62 — Computer-Use Agents
| Capability | Status | Notes |
|---|---|---|
| Screen interaction | MISSING | No screen control |
| Mouse actions | MISSING | No mouse control |
| Keyboard actions | MISSING | No keyboard control |
| File dialogs | MISSING | No dialog control |
| Clipboard | MISSING | No clipboard control |
| Application launch | MISSING | No app launch control |
| Privileged operations | MISSING | No privileged-op control |

### 63 — Memory Safety
| Capability | Status | Notes |
|---|---|---|
| Long-term memory | MISSING | No long-term memory |
| Session memory | PARTIAL | session state |
| Vector stores | MISSING | No vector store |
| Retrieved context | PARTIAL | context in AgentActionDAG |
| Memory writes | MISSING | No memory write control |
| Memory deletion | MISSING | No memory deletion control |
| Memory poisoning | MISSING | No poisoning defense |
| Cross-tenant memory | MISSING | No cross-tenant memory isolation |

### 64 — Agent Supply Chain
| Capability | Status | Notes |
|---|---|---|
| Model tracking | PARTIAL | no explicit model entity |
| System prompt tracking | PARTIAL | reasoning_step captured |
| Tool tracking | PARTIAL | tool field |
| Plugin tracking | MISSING | No plugin model |
| MCP server tracking | MISSING | No MCP server model |
| Package tracking | MISSING | No package SBOM |
| Dependency tracking | MISSING | No dependency graph |
| Version tracking | PARTIAL | policy_version, plan_version |
| Configuration tracking | PARTIAL | config adapters |
| Policy version | PARTIAL | policy_version field |
| SBOM | MISSING | No SBOM generation |

### 65 — Model / Model-Routing Security
| Capability | Status | Notes |
|---|---|---|
| Model identity | MISSING | No model identity |
| Model version | MISSING | No model version |
| Model provider | MISSING | No provider tracking |
| Model change | MISSING | No model change detection |
| Routing decisions | MISSING | No model router |
| Fallback model | MISSING | No fallback |
| Model permissions | MISSING | No model permissions |
| Model-specific policies | MISSING | No model-specific policy |
| Model-specific incidents | MISSING | No model-specific incident tracking |

### 66 — Incident AI Assistant
| Capability | Status | Notes |
|---|---|---|
| Incident summarization | MISSING | No AI summarization |
| Timeline reconstruction | PARTIAL | causal graph |
| Hypothesis proposal | MISSING | No hypothesis engine |
| Risk explanation | PARTIAL | risk engine explanations |
| Recovery candidate suggestions | MISSING | No AI suggestion |
| Uncertainty identification | PARTIAL | limitations field |
| Verification checks | PARTIAL | verification service |

### 67 — AI-Assisted Recovery Planning
| Capability | Status | Notes |
|---|---|---|
| Dependency discovery | PARTIAL | topological order computed |
| Recovery candidate ranking | PARTING | no ranking |
| Compensation suggestions | PARTIAL | compensation_payload |
| Anomaly explanation | PARTIAL | risk engine explanations |
| Incident summarization | MISSING | No AI summarization |
| Deterministic safety gates | IMPLEMENTED | verification required |

### 68 — Self-Protection
| Capability | Status | Notes |
|---|---|---|
| Configuration tampering protection | PARTIAL | no config signature |
| Policy tampering protection | PARTIAL | policy_version tracked |
| Evidence tampering protection | PARTIAL | JSONL with hash-chain idea; no implementation |
| Token manipulation protection | IMPLEMENTED | Ed25519 signatures |
| Unauthorized admin access | PARTIAL | admin bearer token required |
| Recovery-plan manipulation | PARTIAL | plan_hash exists |
| Tenant escape | IMPLEMENTED | tenant scoping |
| Log destruction | PARTIAL | no log tamper detection |
| Disabling verification | PARTIAL | verification_passed flag |
| Disabling containment | PARTIAL | no disable mechanism |

### 69 — Administrative Safety
| Capability | Status | Notes |
|---|---|---|
| Re-authentication | MISSING | No re-auth for admin actions |
| Approvals | IMPLEMENTED | HITL queue |
| Dual control | MISSING | No dual control |
| Explicit confirmation | PARTIAL | no confirmation step |
| Audit | IMPLEMENTED | audit log |
| Reason codes | PARTIAL | decision_reason |
| Break-glass controls | MISSING | No break-glass |
| Emergency mode | MISSING | No emergency mode |

### 70 — Feature Governance
| Capability | Status | Notes |
|---|---|---|
| Feature flags | MISSING | No feature flags |
| Maturity state | PARTIAL | AdapterCapability enum |
| Experimental/production designation | PARTIAL | AdapterCapability |
| Documentation | PARTIAL | docs exist |
| Test suite | IMPLEMENTED | pytest suite |
| Security review state | PARTIAL | security docs exist |
| Rollback strategy | PARTIAL | recovery adapters |

## Architecture Summary

### Existing Architecture
Interlock V4 uses a hexagonal (ports-and-adapters) architecture:
- `app/presentation` — FastAPI routes, middleware, dependency injection
- `app/application` — use cases, DTOs, port interfaces
- `app/domain` — entities, value objects, domain services, repository interfaces
- `app/infrastructure` — persistence (SQLAlchemy + Alembic), security (JWT, bcrypt, Ed25519), Redis, recovery adapters, SSO adapters, audit logging, observability
- `sdk` — Python SDK and LangChain wrapper

### Tech Stack
- Python 3.11+, FastAPI, PostgreSQL/SQLite, Redis
- Ed25519 execution tokens with atomic nonce replay protection
- HS256 JWT access tokens, bcrypt password hashing
- sqlglot SQL parsing, PyYAML policy engine
- Alembic migrations, Next.js web dashboard (frontend present but not fully functional)

### Current Capability Count
- **Implemented**: ~120 capabilities
- **Partial**: ~180 capabilities
- **Missing**: ~700+ capabilities
- **Total meaningful capability slots**: 1000+

### Top P0/P1 Opportunities
1. **P0: Universal state capture and immutable evidence** — strengthen tamper evidence, add Merkle chain, binary-safe capture
2. **P0: Recovery confidence model integration** — wire recovery confidence into risk engine and incident response
3. **P0: Token security hardening** — add audience restriction, context binding, misuse detection
4. **P1: Universal action model** — canonical action model for all adapters
5. **P1: Resource graph and graph queries** — enable "what did this agent touch?" queries
6. **P1: Digital twin / simulation hardening** — expand simulation coverage
7. **P1: Chaos engineering framework** — systematic failure injection
8. **P1: Observability hardening** — OpenTelemetry, structured traces
9. **P2: Cloud/Kubernetes adapters** — AWS, Azure, GCP, K8s recovery
10. **P2: Enterprise security** — real SSO, SCIM, certificate rotation
11. **P2: Dashboard and workbench** — incident timeline UI, recovery workbench
12. **P3: SDK/CLI expansion** — async SDK, full CLI, testing helpers
13. **P3: Scale/performance benchmarks** — realistic workload benchmarks
14. **P3: Property-based testing expansion** — more formal safety properties

### Proposed Implementation Waves
- Wave 1: Architecture hardening, universal state capture, immutable evidence
- Wave 2: P0 security gaps (tokens, policy, identity)
- Wave 3: Containment expansion
- Wave 4: Recovery coverage expansion
- Wave 5: Verification strengthening
- Wave 6: Forensics and evidence chain
- Wave 7: Universal action model
- Wave 8: Resource/dependency graph
- Wave 9: Simulation and digital twin
- Wave 10: Chaos engineering
- Wave 11: MCP/A2A security
- Wave 12: Agent framework integrations
- Wave 13: Cloud/infrastructure adapters
- Wave 14: Enterprise security
- Wave 15: Observability
- Wave 16: Developer experience
- Wave 17: Scale/performance
- Wave 18: Security research
- Wave 19: AI-assisted security/recovery
- Wave 20: Final hardening

### Dependencies
- Wave 1 must complete before Wave 2 (foundational hardening)
- Wave 7 (universal action model) enables Wave 13 (cloud adapters)
- Wave 8 (resource graph) enables Wave 9 (simulation) and Wave 15 (observability)
- Wave 11 (MCP/A2A) depends on Wave 1 (identity hardening)
- Enterprise security (Wave 14) depends on Wave 2 (token hardening)

### Risks
- **Scale**: 1000+ capabilities is a multi-year program; must be bounded per wave
- **Complexity**: Recovery adapters for cloud/K8s require real infrastructure testing
- **Compatibility**: Must preserve existing API contracts
- **Performance**: Graph queries and large-scale benchmarks may reveal bottlenecks
- **Security**: New features must not weaken existing fail-closed semantics
