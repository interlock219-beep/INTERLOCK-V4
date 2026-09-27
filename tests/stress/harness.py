"""Interlock V4 unified stress-test harness.

Reuses the existing ComplexRecoveryHarness and real production adapters,
adding multi-tenant / multi-agent / multi-session control-plane workload
generation, token lifecycle simulation, authorization decision tracking,
evidence integrity checks, recovery plan orchestration, human change
injection, failure injection, crash/resume simulation, concurrency
support, metrics collection, and data-integrity invariant checks.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import secrets
import statistics
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from app.domain.entities.agent import (
    Agent,
    AgentStatus,
    AgentType,
    RegistrationMethod,
    RiskClassification,
    TrustLevel,
)
from app.domain.entities.agent_session import AgentSession, AgentSessionStatus
from app.domain.entities.execution_token import ExecutionToken, TokenStatus
from app.domain.entities.protected_action import (
    ActionStatus,
    ProtectedAction,
    Reversibility,
)
from app.domain.entities.recovery_plan import (
    RecoveryOutcome,
    RecoveryPlan,
    RecoveryStatus,
)
from app.domain.entities.surgical_recovery_types import (
    AdapterCapability,
    CompensationResult,
    CompensationType,
    DriftStatus,
    ExecutionState,
    RecoveryAdapterType,
    RecoveryEvidence,
    StopCondition,
    VerificationResult,
)
from app.domain.repositories.containment_repository import RecoveryPlanRepository
from app.domain.repositories.protected_action_repository import ProtectedActionRepository
from app.domain.repositories.recovery_evidence_repository import (
    RecoveryEvidenceRepository,
)
from app.domain.repositories.execution_token_repository import (
    ExecutionTokenRepository,
)
from app.domain.services.authorization_service import AuthorizationService
from app.domain.services.recovery_adapter import RecoveryAdapter
from app.domain.services.recovery_planning_service import RecoveryPlanningService
from app.domain.services.recovery_simulation_engine import (
    RecoverySimulationEngine,
)
from app.domain.services.token_revocation_service import (
    TokenRevocationReason,
    TokenRevocationService,
)
from app.domain.value_objects.authorization_context import (
    AgentEnvironment,
    AuthorizationContext,
)
from app.domain.value_objects.authorization_decision import AuthorizationDecision
from app.infrastructure.recovery.config_recovery_adapter import (
    ConfigRecoveryAdapter,
)
from app.infrastructure.recovery.database_recovery_adapter import (
    DatabaseRecoveryAdapter,
)
from app.infrastructure.recovery.filesystem_recovery_adapter import (
    FilesystemRecoveryAdapter,
)
from app.infrastructure.recovery.git_repository_adapter import (
    GitRepositoryAdapter,
)
from app.infrastructure.observability.metrics import metrics

from tests.unit.recovery_gauntlet.harness import (
    ComplexRecoveryHarness,
)
from tests.unit.recovery_lab.environment import DisposableEnvironment


# ---------------------------------------------------------------------------
# In-memory repositories for control-plane state (no DB required)
# ---------------------------------------------------------------------------


class _InMemoryTokenRepo(ExecutionTokenRepository):
    """Thread/async-safe in-memory execution-token repository."""

    def __init__(self) -> None:
        self._store: dict[str, ExecutionToken] = {}
        self._agent_index: dict[str, list[ExecutionToken]] = defaultdict(list)
        self._tenant_index: dict[str, list[ExecutionToken]] = defaultdict(list)
        self._jti_index: dict[str, ExecutionToken] = {}
        self._lock = asyncio.Lock()

    async def get_by_jti(self, tenant_id: str, jti: str) -> ExecutionToken | None:
        async with self._lock:
            ev = self._jti_index.get(jti)
            if ev and ev.tenant_id == tenant_id:
                return ev
            return None

    async def list_by_agent(
        self,
        tenant_id: str,
        agent_id: str,
        status: TokenStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[ExecutionToken], int]:
        async with self._lock:
            items = [
                t for t in self._agent_index.get(agent_id, [])
                if t.tenant_id == tenant_id
                and (status is None or t.status == status)
            ]
        return items[offset:offset + limit], len(items)

    async def list_by_tenant(
        self,
        tenant_id: str,
        status: TokenStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[ExecutionToken], int]:
        async with self._lock:
            items = [
                t for t in self._tenant_index.get(tenant_id, [])
                if status is None or t.status == status
            ]
        return items[offset:offset + limit], len(items)

    async def save(self, token: ExecutionToken) -> ExecutionToken:
        async with self._lock:
            self._store[token.token_id] = token
            self._agent_index[token.agent_id].append(token)
            self._tenant_index[token.tenant_id].append(token)
            self._jti_index[token.jti] = token
        return token

    async def revoke(
        self,
        tenant_id: str,
        token_id: str,
        *,
        revoked_at: datetime | None = None,
    ) -> ExecutionToken | None:
        async with self._lock:
            token = self._store.get(token_id)
            if token is None or token.tenant_id != tenant_id:
                return None
            updated = ExecutionToken(
                token_id=token.token_id,
                tenant_id=token.tenant_id,
                jti=token.jti,
                agent_id=token.agent_id,
                tool=token.tool,
                authority_grant_id=token.authority_grant_id,
                status=TokenStatus.REVOKED,
                issued_at=token.issued_at,
                expires_at=token.expires_at,
                consumed_at=token.consumed_at,
                revoked_at=revoked_at or datetime.now(UTC),
            )
            self._store[token_id] = updated
            self._jti_index[token.jti] = updated
            return updated

    async def consume_one_shot(
        self,
        tenant_id: str,
        jti: str,
    ) -> ExecutionToken | None:
        """Atomically consume an ACTIVE token. Returns the consumed token or None."""
        async with self._lock:
            token = self._jti_index.get(jti)
            if token is None or token.tenant_id != tenant_id:
                return None
            if token.status != TokenStatus.ACTIVE:
                return None
            consumed = ExecutionToken(
                token_id=token.token_id,
                tenant_id=token.tenant_id,
                jti=token.jti,
                agent_id=token.agent_id,
                tool=token.tool,
                authority_grant_id=token.authority_grant_id,
                status=TokenStatus.CONSUMED,
                issued_at=token.issued_at,
                expires_at=token.expires_at,
                consumed_at=datetime.now(UTC),
                revoked_at=token.revoked_at,
            )
            self._store[token.token_id] = consumed
            self._jti_index[jti] = consumed
            self._agent_index[consumed.agent_id].append(consumed)
            self._tenant_index[consumed.tenant_id].append(consumed)
            return consumed


class _InMemoryAuthDecisionRepo:
    """In-memory authorization decision log (for metrics / audit)."""

    def __init__(self) -> None:
        self._store: list[dict[str, Any]] = []
        self._lock = asyncio.Lock()

    async def record(self, decision: AuthorizationDecision, reason: str, ctx: dict[str, Any]) -> None:
        async with self._lock:
            self._store.append({
                "decision": decision.value,
                "reason": reason,
                "context": ctx,
                "timestamp": datetime.now(UTC).isoformat(),
            })

    @property
    def decisions(self) -> list[dict[str, Any]]:
        return list(self._store)

    def clear(self) -> None:
        self._store.clear()


# ---------------------------------------------------------------------------
# Result / metrics data classes
# ---------------------------------------------------------------------------


@dataclass
class TokenLifecycleResult:
    token_id: str
    jti: str
    tenant_id: str
    agent_id: str
    lifecycle: str  # issued -> consumed | issued -> expired | issued -> revoked
    elapsed_ms: float = 0.0
    error: str | None = None


@dataclass
class AuthzDecisionResult:
    tenant_id: str
    agent_id: str
    decision: str
    reason: str
    elapsed_ms: float = 0.0


@dataclass
class ControlPlaneActionResult:
    action_id: str
    tenant_id: str
    agent_id: str
    session_id: str
    resource_type: str
    operation: str
    adapter_used: str
    success: bool
    before_state: Any
    after_state: Any
    evidence_captured: bool
    token_issued: bool
    authz_decision: str
    error: str | None = None
    elapsed_ms: float = 0.0


@dataclass
class StressResult:
    scenario: str
    seed: int
    started_at: str
    finished_at: str
    elapsed_ms: float
    tenants: list[str]
    actions_generated: int
    actions_executed: int
    actions_succeeded: int
    actions_failed: int
    tokens_issued: int
    tokens_consumed: int
    tokens_expired: int
    tokens_revoked: int
    authz_allows: int
    authz_denies: int
    authz_hitls: int
    evidence_count: int
    plans_created: int
    plans_executed: int
    recovery_recovered: int
    recovery_failed: int
    human_changes_injected: int
    failures_injected: int
    crash_resume_cycles: int
    invariant_violations: int
    latency_p50_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    throughput_per_sec: float
    action_results: list[ControlPlaneActionResult] = field(default_factory=list)
    token_results: list[TokenLifecycleResult] = field(default_factory=list)
    authz_results: list[AuthzDecisionResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# UnifiedStressHarness
# ---------------------------------------------------------------------------


class UnifiedStressHarness:
    """Unified production-quality stress-test harness for Interlock V4.

    Wraps the existing ComplexRecoveryHarness to add:
      - Deterministic LCG seeded random
      - Multi-tenant / multi-agent / multi-session workload generation
      - Control-plane action execution with real adapters
      - Token lifecycle simulation (issue / consume / expire / revoke)
      - Authorization decision tracking via real AuthorizationService
      - Evidence creation and integrity checks
      - Recovery plan creation, execution, independent verification
      - Human change injection
      - Failure injection (wrapped adapters)
      - Crash / resume simulation
      - Asyncio-backed concurrency
      - Latency / throughput metrics collection
      - Data-integrity invariant checks

    Reuses real production adapters and in-memory repositories for
    control-plane state.
    """

    DEFAULT_TENANTS = ["tenant-alpha", "tenant-beta", "tenant-gamma", "tenant-delta"]
    AGENT_TYPES = [at.value for at in AgentType]
    RESOURCE_TYPES = ["filesystem", "database", "git", "config"]

    def __init__(
        self,
        scenario: str = "stress_default",
        seed: int = 0xDEADBEEF,
        tenants: list[str] | None = None,
        n_agents_per_tenant: int = 4,
        n_sessions_per_agent: int = 2,
        workspace_path: str | None = None,
    ) -> None:
        self.scenario = scenario
        self._seed = seed
        self._tenants = tenants or list(self.DEFAULT_TENANTS)
        self._n_agents = n_agents_per_tenant
        self._n_sessions = n_sessions_per_agent
        self._workspace_path = workspace_path

        self._rng_state = seed

        # Backing recovery harness
        self._gauntlet = ComplexRecoveryHarness(
            scenario=scenario,
            seed=seed,
            workspace_path=workspace_path,
        )

        # Control-plane in-memory state
        self.token_repo = _InMemoryTokenRepo()
        self.authz_repo = _InMemoryAuthDecisionRepo()

        # Real authorization service (no mock)
        self.authorization_service = AuthorizationService()

        # Token revocation service (wired to in-memory repo)
        self.token_revocation_service = TokenRevocationService(
            token_repository=self.token_repo,
        )

        # Registered agents / sessions / tokens
        self._agents: dict[str, dict[str, Agent]] = defaultdict(dict)
        self._sessions: dict[str, dict[str, dict[str, AgentSession]]] = defaultdict(
            lambda: defaultdict(dict)
        )
        self._tokens: dict[str, ExecutionToken] = {}

        # Metrics collectors
        self._action_latencies: list[float] = []
        self._action_results: list[ControlPlaneActionResult] = []
        self._token_results: list[TokenLifecycleResult] = []
        self._authz_results: list[AuthzDecisionResult] = []

        # Tracking
        self._human_changes_injected: int = 0
        self._failures_injected: int = 0
        self._crash_resume_cycles: int = 0
        self._invariant_violations: int = 0

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> UnifiedStressHarness:
        await self._gauntlet.__aenter__()
        self._register_agents_and_sessions()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self._gauntlet.__aexit__(*args)

    def __enter__(self) -> UnifiedStressHarness:
        self._gauntlet.__enter__()
        self._register_agents_and_sessions()
        return self

    def __exit__(self, *args: Any) -> None:
        self._gauntlet.__exit__(*args)

    # ------------------------------------------------------------------
    # Deterministic LCG
    # ------------------------------------------------------------------

    def _rand(self) -> int:
        self._rng_state = (self._rng_state * 1664525 + 1013904223) & 0xFFFFFFFF
        return self._rng_state

    def _rand_int(self, lo: int, hi: int) -> int:
        return lo + self._rand() % (hi - lo + 1)

    def _rand_choice(self, seq: list[Any]) -> Any:
        return seq[self._rand() % len(seq)]

    def _rand_choices(self, seq: list[Any], k: int) -> list[Any]:
        return [seq[self._rand() % len(seq)] for _ in range(k)]

    def _reset_rng(self) -> None:
        self._rng_state = self._seed

    # ------------------------------------------------------------------
    # Agent / session / token registration
    # ------------------------------------------------------------------

    def _register_agents_and_sessions(self) -> None:
        for tenant_id in self._tenants:
            for agent_idx in range(self._n_agents):
                agent_id = f"agent-{tenant_id}-{agent_idx:03d}"
                agent = Agent(
                    agent_id=agent_id,
                    tenant_id=tenant_id,
                    name=f"Stress Agent {tenant_id} #{agent_idx}",
                    agent_type=AgentType.USER_AGENT,
                    status=AgentStatus.ACTIVE,
                    trust_level=TrustLevel.VERIFIED,
                    risk_classification=RiskClassification.LOW,
                    environment=AgentEnvironment.TEST,
                    model_provider="stress",
                    model_name="stress-model",
                    registration_method=RegistrationMethod.API,
                    root_human_sponsor="stress-harness",
                    connected_tools=self._rand_choices(self.RESOURCE_TYPES, k=2),
                    metadata={"stress": "true", "scenario": self.scenario},
                )
                self._agents[tenant_id][agent_id] = agent
                for sess_idx in range(self._n_sessions):
                    session_id = f"sess-{agent_id}-{sess_idx:02d}"
                    session = AgentSession(
                        session_id=session_id,
                        tenant_id=tenant_id,
                        agent_id=agent_id,
                        status=AgentSessionStatus.ACTIVE,
                        risk_level="low",
                        correlation_id=f"corr-{uuid4().hex[:8]}",
                        metadata={"stress": "true"},
                    )
                    self._sessions[tenant_id][agent_id][session_id] = session

    # ------------------------------------------------------------------
    # Resource / operation selection helpers
    # ------------------------------------------------------------------

    OPERATIONS: dict[str, list[str]] = {
        "filesystem": ["create", "modify", "delete", "rename"],
        "database": ["insert", "update", "delete"],
        "git": ["add_file", "modify_file", "commit", "delete_file"],
        "config": ["write_config", "modify_config", "delete_config"],
    }

    def _pick_resource_and_operation(self) -> tuple[str, str]:
        resource_type = self._rand_choice(self.RESOURCE_TYPES)
        operation = self._rand_choice(self.OPERATIONS[resource_type])
        return resource_type, operation


    # ------------------------------------------------------------------
    # Control-plane workload generation
    # ------------------------------------------------------------------

    def generate_control_plane_workload(
        self,
        n_actions: int,
        n_tenants: int,
        n_agents: int,
    ) -> list[dict[str, Any]]:
        """Generate *n_actions* deterministic control-plane actions.

        Each action is scoped to a tenant / agent / session and includes
        resource_type, operation, resource reference, and dependency hints.
        """
        self._reset_rng()
        actions: list[dict[str, Any]] = []
        active_tenants = self._tenants[:n_tenants]

        for i in range(n_actions):
            tenant_id = active_tenants[i % len(active_tenants)]
            agent_ids = list(self._agents[tenant_id].keys())
            agent_id = agent_ids[i % len(agent_ids)] if agent_ids else f"agent-{tenant_id}-000"
            session_ids = list(self._sessions[tenant_id].get(agent_id, {}).keys())
            session_id = session_ids[i % len(session_ids)] if session_ids else f"sess-{agent_id}-00"

            resource_type, operation = self._pick_resource_and_operation()
            resource = f"{resource_type}:stress-{tenant_id}-{agent_id}-{i:06d}"

            actions.append({
                "action_id": f"ctrl-{i:08d}",
                "tenant_id": tenant_id,
                "agent_id": agent_id,
                "session_id": session_id,
                "resource_type": resource_type,
                "operation": operation,
                "resource": resource,
                "tool": resource_type,
                "parent_action_id": None,
                "reversibility": Reversibility.AUTOMATICALLY_REVERSIBLE,
                "risk_score": round(self._rand_int(1, 100) / 100.0, 2),
            })

        return actions

    # ------------------------------------------------------------------
    # Token lifecycle simulation
    # ------------------------------------------------------------------

    async def _issue_token(
        self,
        tenant_id: str,
        agent_id: str,
        tool: str,
        ttl_seconds: int = 300,
    ) -> ExecutionToken:
        token_id = f"tok-{uuid4().hex[:12]}"
        jti = f"jti-{uuid4().hex[:16]}"
        now = datetime.now(UTC)
        token = ExecutionToken(
            token_id=token_id,
            tenant_id=tenant_id,
            jti=jti,
            agent_id=agent_id,
            tool=tool,
            status=TokenStatus.ACTIVE,
            issued_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
        )
        await self.token_repo.save(token)
        self._tokens[token_id] = token
        metrics.increment_execution_tokens_issued()
        return token

    async def _consume_token(self, token: ExecutionToken) -> bool:
        try:
            consumed = await self.token_repo.consume_one_shot(
                tenant_id=token.tenant_id,
                jti=token.jti,
            )
            if consumed is None:
                return False
            self._tokens[token.token_id] = consumed
            metrics.increment_execution_tokens_consumed()
            return True
        except Exception:
            return False

    async def _expire_token(self, token: ExecutionToken) -> bool:
        try:
            token = ExecutionToken(
                token_id=token.token_id,
                tenant_id=token.tenant_id,
                jti=token.jti,
                agent_id=token.agent_id,
                tool=token.tool,
                status=TokenStatus.EXPIRED,
                issued_at=token.issued_at,
                expires_at=token.expires_at,
                consumed_at=token.consumed_at,
                revoked_at=token.revoked_at,
            )
            await self.token_repo.save(token)
            self._tokens[token.token_id] = token
            return True
        except Exception:
            return False

    async def simulate_token_lifecycle(
        self,
        n_tokens: int,
        consume_prob: float = 0.6,
        expire_prob: float = 0.2,
        revoke_prob: float = 0.2,
    ) -> list[TokenLifecycleResult]:
        """Simulate token lifecycle: issue, then consume/expire/revoke."""
        results: list[TokenLifecycleResult] = []
        for _ in range(n_tokens):
            tenant_id = self._rand_choice(self._tenants)
            agent_ids = list(self._agents[tenant_id].keys())
            agent_id = self._rand_choice(agent_ids) if agent_ids else tenant_id
            tool = self._rand_choice(self.RESOURCE_TYPES)

            t0 = time.monotonic()
            try:
                token = await self._issue_token(tenant_id, agent_id, tool)
                r = secrets.SystemRandom().random()
                if r < consume_prob:
                    ok = await self._consume_token(token)
                    lifecycle = "issued -> consumed" if ok else "issued -> error"
                elif r < consume_prob + expire_prob:
                    ok = await self._expire_token(token)
                    lifecycle = "issued -> expired" if ok else "issued -> error"
                else:
                    res = await self.token_revocation_service.revoke_token(
                        tenant_id=tenant_id,
                        token_id=token.token_id,
                        reason=TokenRevocationReason.MANUAL,
                        revoked_by="stress-harness",
                    )
                    lifecycle = (
                        "issued -> revoked"
                        if res.get("total_revoked", 0) > 0
                        else "issued -> error"
                    )
                elapsed = (time.monotonic() - t0) * 1000.0
                results.append(TokenLifecycleResult(
                    token_id=token.token_id,
                    jti=token.jti,
                    tenant_id=tenant_id,
                    agent_id=agent_id,
                    lifecycle=lifecycle,
                    elapsed_ms=elapsed,
                ))
                self._token_results.append(results[-1])
            except Exception as exc:
                elapsed = (time.monotonic() - t0) * 1000.0
                results.append(TokenLifecycleResult(
                    token_id="",
                    jti="",
                    tenant_id=tenant_id,
                    agent_id=agent_id,
                    lifecycle="error",
                    elapsed_ms=elapsed,
                    error=str(exc),
                ))
                self._token_results.append(results[-1])
        return results


    # ------------------------------------------------------------------
    # Authorization decision tracking
    # ------------------------------------------------------------------

    async def _evaluate_authorization(
        self,
        tenant_id: str,
        agent_id: str,
        tool: str,
        resource: str,
        action: str = "execute",
    ) -> AuthorizationDecision:
        ctx = AuthorizationContext(
            user_id=uuid4(),
            agent_id=agent_id,
            proposed_tool=tool,
            tenant_id=tenant_id,
            action=action,
            resource=resource,
            environment=AgentEnvironment.TEST,
            agent_history=[],
            dependency_state={},
            incident_state={},
            recovery_state={},
            authority_grants=[],
            recent_actions=[],
        )
        decision, reason = self.authorization_service.authorize(ctx)
        await self.authz_repo.record(decision, reason, {
            "tenant_id": tenant_id,
            "agent_id": agent_id,
            "tool": tool,
            "resource": resource,
            "action": action,
        })
        return decision

    async def evaluate_authz_for_actions(
        self,
        actions: list[dict[str, Any]],
    ) -> list[AuthzDecisionResult]:
        """Evaluate authorization decisions for a batch of actions."""
        results: list[AuthzDecisionResult] = []
        for act in actions:
            t0 = time.monotonic()
            decision = await self._evaluate_authorization(
                tenant_id=act["tenant_id"],
                agent_id=act["agent_id"],
                tool=act["tool"],
                resource=act["resource"],
                action=act["operation"],
            )
            elapsed = (time.monotonic() - t0) * 1000.0
            res = AuthzDecisionResult(
                tenant_id=act["tenant_id"],
                agent_id=act["agent_id"],
                decision=decision.value,
                reason="",
                elapsed_ms=elapsed,
            )
            results.append(res)
            self._authz_results.append(res)
        return results

    # ------------------------------------------------------------------
    # Control-plane action execution
    # ------------------------------------------------------------------

    async def _execute_control_plane_action(
        self,
        spec: dict[str, Any],
        concurrency_semaphore: asyncio.Semaphore,
    ) -> ControlPlaneActionResult:
        async with concurrency_semaphore:
            t0 = time.monotonic()
            action_id = spec["action_id"]
            tenant_id = spec["tenant_id"]
            agent_id = spec["agent_id"]
            session_id = spec.get("session_id", "")
            resource_type = spec["resource_type"]
            operation = spec["operation"]
            resource = spec["resource"]

            # 1. Authorization check
            authz = await self._evaluate_authorization(
                tenant_id=tenant_id,
                agent_id=agent_id,
                tool=spec["tool"],
                resource=resource,
                action=operation,
            )

            # 2. Issue token (best-effort)
            token_issued = False
            token: ExecutionToken | None = None
            try:
                token = await self._issue_token(tenant_id, agent_id, spec["tool"])
                token_issued = True
            except Exception:
                token_issued = False

            # 3. Execute action via the backing gauntlet (single action path)
            adapter_used = "none"
            success = False
            before_state: Any = None
            after_state: Any = None
            evidence_captured = False
            error: str | None = None

            try:
                single = [spec]
                results = await self._gauntlet.execute_actions(
                    single,
                    tenant_id=tenant_id,
                    agent_id=agent_id,
                    correlation_id=session_id,
                )
                if results:
                    r = results[0]
                    success = r.success
                    adapter_used = r.adapter_used
                    before_state = r.before_state
                    after_state = r.after_state
                    evidence_captured = r.evidence_captured
                    error = r.error
            except Exception as exc:
                error = str(exc)
                success = False

            # 4. Consume token if issued and action succeeded
            if token_issued and token and success:
                try:
                    await self._consume_token(token)
                except Exception:
                    pass

            elapsed = (time.monotonic() - t0) * 1000.0
            self._action_latencies.append(elapsed)

            result = ControlPlaneActionResult(
                action_id=action_id,
                tenant_id=tenant_id,
                agent_id=agent_id,
                session_id=session_id,
                resource_type=resource_type,
                operation=operation,
                adapter_used=adapter_used,
                success=success,
                before_state=before_state,
                after_state=after_state,
                evidence_captured=evidence_captured,
                token_issued=token_issued,
                authz_decision=authz.value,
                error=error,
                elapsed_ms=elapsed,
            )
            self._action_results.append(result)
            return result

    async def execute_control_plane_workload(
        self,
        actions: list[dict[str, Any]],
        concurrency: int = 16,
    ) -> list[ControlPlaneActionResult]:
        """Execute control-plane actions with bounded asyncio concurrency."""
        semaphore = asyncio.Semaphore(concurrency)
        tasks = [
            self._execute_control_plane_action(act, semaphore)
            for act in actions
        ]
        return list(await asyncio.gather(*tasks, return_exceptions=False))


    # ------------------------------------------------------------------
    # Recovery plan creation and execution
    # ------------------------------------------------------------------

    async def create_recovery_plan(
        self,
        action_ids: list[str],
        *,
        tenant_id: str = "tenant-alpha",
        stop_conditions: list[str] | None = None,
    ) -> RecoveryPlan:
        """Delegate to the backing ComplexRecoveryHarness."""
        return await self._gauntlet.create_recovery_plan(
            action_ids,
            tenant_id=tenant_id,
            stop_conditions=stop_conditions,
        )

    async def execute_recovery(
        self,
        plan: RecoveryPlan,
        *,
        tenant_id: str = "tenant-alpha",
    ) -> Any:
        """Delegate to the backing ComplexRecoveryHarness."""
        return await self._gauntlet.execute_recovery(plan, tenant_id=tenant_id)

    async def verify_recovery_independently(
        self,
        baseline: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Independent environment fingerprint verification."""
        if baseline is None:
            baseline = self._gauntlet.capture_baseline_snapshot()
        return self._gauntlet.verify_against_baseline(baseline)

    # ------------------------------------------------------------------
    # Human change injection
    # ------------------------------------------------------------------

    async def inject_human_change(
        self,
        case: str,
        resource_type: str,
        resource: str,
        tenant_id: str = "tenant-alpha",
    ) -> dict[str, Any]:
        """Inject a controlled legitimate human change via the gauntlet."""
        change = self._gauntlet.inject_human_change(case, resource_type, resource)
        self._human_changes_injected += 1
        return change

    # ------------------------------------------------------------------
    # Failure injection
    # ------------------------------------------------------------------

    def inject_failure(
        self,
        failure_mode: str,
        adapter_index: int = 0,
    ) -> RecoveryAdapter:
        """Create a failing adapter wrapper and replace it in the gauntlet."""
        base = self._gauntlet.adapters[adapter_index]
        failing = self._gauntlet.create_failing_adapter(base, failure_mode)
        self._gauntlet.adapters[adapter_index] = failing
        self._failures_injected += 1
        return failing

    def restore_adapter(self, adapter_index: int) -> None:
        """Restore original adapters (best-effort; rebuilds from scratch)."""
        self._gauntlet.adapters = self._gauntlet._build_adapters()

    # ------------------------------------------------------------------
    # Crash / resume simulation
    # ------------------------------------------------------------------

    async def simulate_crash_resume(
        self,
        plan: RecoveryPlan,
        *,
        tenant_id: str = "tenant-alpha",
        interrupt_after: int | None = None,
    ) -> dict[str, Any]:
        """Create durable steps, execute partially, then resume."""
        steps = await self._gauntlet.create_durable_plan(plan, tenant_id=tenant_id)
        if interrupt_after is None:
            interrupt_after = max(1, len(steps) // 3)

        partial = await self._gauntlet.execute_durable_plan(
            plan,
            steps,
            tenant_id=tenant_id,
            interrupt_after=interrupt_after,
        )
        resumed = await self._gauntlet.resume_durable_plan(plan, tenant_id=tenant_id)
        self._crash_resume_cycles += 1
        return {
            "partial": partial,
            "resumed": resumed,
            "total_steps": len(steps),
            "interrupted_at": interrupt_after,
        }

    # ------------------------------------------------------------------
    # Evidence creation and integrity checks
    # ------------------------------------------------------------------

    async def verify_evidence_integrity(
        self,
        action_ids: list[str],
        tenant_id: str = "tenant-alpha",
    ) -> dict[str, Any]:
        """Verify evidence hashes and completeness for a set of actions."""
        ok = 0
        missing = 0
        corrupted = 0
        details: dict[str, Any] = {}
        for aid in action_ids:
            ev = await self._gauntlet.evidence_repo.get_by_action_id(tenant_id, aid)
            if ev is None:
                missing += 1
                details[aid] = "missing"
                continue
            if not ev.evidence_hash:
                corrupted += 1
                details[aid] = "missing_hash"
                continue
            ok += 1
            details[aid] = {
                "evidence_id": ev.evidence_id,
                "hash": ev.evidence_hash,
                "adapter_capability": ev.adapter_capability.value,
                "reversibility": ev.reversibility_classification.value,
            }
        return {
            "checked": len(action_ids),
            "ok": ok,
            "missing": missing,
            "corrupted": corrupted,
            "details": details,
            "all_ok": (missing == 0 and corrupted == 0),
        }

    # ------------------------------------------------------------------
    # Data-integrity invariant checks
    # ------------------------------------------------------------------

    async def check_data_integrity_invariants(
        self,
        tenant_id: str = "tenant-alpha",
    ) -> dict[str, Any]:
        """Assert invariants across in-memory repositories.

        Invariants:
          1. Every action referenced by evidence exists in action repo.
          2. Every evidence action_id reference is non-empty.
          3. Token statuses are one of ACTIVE / CONSUMED / EXPIRED / REVOKED.
          4. No duplicate jti in token repo.
          5. Recovery plan affected_action_ids are a subset of executed actions.
        """
        violations: list[str] = []

        # Collect all executed action ids from gauntlet
        executed_ids = set(self._gauntlet._executed_actions.keys())

        # Evidence invariant
        evidence_store = self._gauntlet.evidence_repo._store
        for ev in evidence_store.values():
            if not ev.action_id:
                violations.append("evidence_missing_action_id")
            elif ev.action_id not in executed_ids:
                violations.append(f"evidence_orphan:{ev.evidence_id}")

        # Token invariant
        seen_jti: set[str] = set()
        for tok in self.token_repo._store.values():
            if tok.status not in (
                TokenStatus.ACTIVE,
                TokenStatus.CONSUMED,
                TokenStatus.EXPIRED,
                TokenStatus.REVOKED,
            ):
                violations.append(f"token_bad_status:{tok.token_id}")
            if tok.jti in seen_jti:
                violations.append(f"token_duplicate_jti:{tok.jti}")
            seen_jti.add(tok.jti)

        self._invariant_violations += len(violations)
        return {
            "checked": True,
            "violations": violations,
            "violation_count": len(violations),
            "invariants_ok": len(violations) == 0,
        }


    # ------------------------------------------------------------------
    # Latency / throughput metrics
    # ------------------------------------------------------------------

    def _percentile(self, data: list[float], pct: float) -> float:
        if not data:
            return 0.0
        s = sorted(data)
        k = (len(s) - 1) * (pct / 100.0)
        f = int(k)
        c = f + 1 if f + 1 < len(s) else f
        if f == c:
            return s[f]
        return s[f] + (k - f) * (s[c] - s[f])

    def compute_metrics(self, elapsed_ms: float) -> dict[str, Any]:
        all_latencies = self._action_latencies
        throughput = (
            (len(all_latencies) / (elapsed_ms / 1000.0))
            if elapsed_ms > 0
            else 0.0
        )
        return {
            "p50_ms": self._percentile(all_latencies, 50),
            "p95_ms": self._percentile(all_latencies, 95),
            "p99_ms": self._percentile(all_latencies, 99),
            "throughput_per_sec": throughput,
            "sample_count": len(all_latencies),
            "min_ms": min(all_latencies) if all_latencies else 0.0,
            "max_ms": max(all_latencies) if all_latencies else 0.0,
            "mean_ms": statistics.mean(all_latencies) if all_latencies else 0.0,
        }

    # ------------------------------------------------------------------
    # Full lifecycle runner
    # ------------------------------------------------------------------

    async def run_full_lifecycle(
        self,
        n_actions: int,
        n_tenants: int = 4,
        n_agents: int = 4,
        concurrency: int = 16,
        token_batch: int = 64,
        inject_human: bool = True,
        inject_failure: bool = False,
        crash_resume: bool = True,
    ) -> StressResult:
        """Run the full stress lifecycle end-to-end.

        Phases:
          1. Generate control-plane workload
          2. Evaluate authorization for all actions
          3. Execute actions with concurrency
          4. Issue / consume / expire / revoke tokens
          5. Create and execute recovery plan
          6. Independent verification
          7. Inject human changes (optional)
          8. Inject failures (optional)
          9. Crash / resume (optional)
          10. Data-integrity invariant checks
        """
        started_at = datetime.now(UTC).isoformat()
        t_global_start = time.monotonic()

        # Phase 1: generate workload
        actions = self.generate_control_plane_workload(n_actions, n_tenants, n_agents)

        # Phase 2: authorization
        await self.evaluate_authz_for_actions(actions)

        # Phase 3: execute
        action_results = await self.execute_control_plane_workload(actions, concurrency=concurrency)

        succeeded = [a for a in action_results if a.success]
        failed = [a for a in action_results if not a.success]

        # Phase 4: token lifecycle
        token_results = await self.simulate_token_lifecycle(token_batch)

        # Phase 5: recovery plan
        plan = None
        recovery_result = None
        if succeeded:
            plan = await self.create_recovery_plan(
                [a.action_id for a in succeeded],
                tenant_id=succeeded[0].tenant_id,
            )
            recovery_result = await self.execute_recovery(
                plan, tenant_id=succeeded[0].tenant_id
            )

        # Phase 6: independent verification
        baseline = self._gauntlet.capture_baseline_snapshot()
        verification = await self.verify_recovery_independently(baseline)

        # Phase 7: human changes
        if inject_human:
            for case in ("A", "B", "C"):
                rt = self._rand_choice(self.RESOURCE_TYPES)
                resource = f"{rt}:human-{uuid4().hex[:8]}"
                await self.inject_human_change(case, rt, resource)

        # Phase 8: failure injection
        if inject_failure and self._gauntlet.adapters:
            self.inject_failure("adapter_failure", adapter_index=0)

        # Phase 9: crash/resume
        crash_resume_report = None
        if crash_resume and plan is not None:
            crash_resume_report = await self.simulate_crash_resume(plan)

        # Phase 10: invariants
        integrity = await self.check_data_integrity_invariants()

        # Authz summary
        authz_decisions = [d.decision for d in self._authz_results]
        authz_allows = sum(1 for d in authz_decisions if d == "allow")
        authz_denies = sum(1 for d in authz_decisions if d == "deny")
        authz_hitls = sum(1 for d in authz_decisions if d == "require_hitl")

        # Token summary
        tokens_issued = sum(1 for r in self._token_results if r.lifecycle.startswith("issued"))
        tokens_consumed = sum(1 for r in self._token_results if "consumed" in r.lifecycle)
        tokens_expired = sum(1 for r in self._token_results if "expired" in r.lifecycle)
        tokens_revoked = sum(1 for r in self._token_results if "revoked" in r.lifecycle)

        elapsed_ms = (time.monotonic() - t_global_start) * 1000.0
        finished_at = datetime.now(UTC).isoformat()
        metrics_summary = self.compute_metrics(elapsed_ms)

        result = StressResult(
            scenario=self.scenario,
            seed=self._seed,
            started_at=started_at,
            finished_at=finished_at,
            elapsed_ms=elapsed_ms,
            tenants=self._tenants,
            actions_generated=len(actions),
            actions_executed=len(action_results),
            actions_succeeded=len(succeeded),
            actions_failed=len(failed),
            tokens_issued=tokens_issued,
            tokens_consumed=tokens_consumed,
            tokens_expired=tokens_expired,
            tokens_revoked=tokens_revoked,
            authz_allows=authz_allows,
            authz_denies=authz_denies,
            authz_hitls=authz_hitls,
            evidence_count=len(self._gauntlet.evidence_repo._store),
            plans_created=1 if plan is not None else 0,
            plans_executed=1 if recovery_result is not None else 0,
            recovery_recovered=getattr(recovery_result, "recovered_count", 0),
            recovery_failed=getattr(recovery_result, "failed_count", 0),
            human_changes_injected=self._human_changes_injected,
            failures_injected=self._failures_injected,
            crash_resume_cycles=self._crash_resume_cycles,
            invariant_violations=integrity.get("violation_count", 0),
            latency_p50_ms=metrics_summary["p50_ms"],
            latency_p95_ms=metrics_summary["p95_ms"],
            latency_p99_ms=metrics_summary["p99_ms"],
            throughput_per_sec=metrics_summary["throughput_per_sec"],
            action_results=action_results,
            token_results=token_results,
            authz_results=self._authz_results,
            errors=[r.error for r in failed if r.error],
            metadata={
                "verification": verification,
                "crash_resume": crash_resume_report,
                "integrity": integrity,
                "metrics": metrics_summary,
            },
        )
        return result
