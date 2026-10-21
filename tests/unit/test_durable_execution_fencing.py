"""WP-2: durable execution fencing at the write boundary.

Regression coverage for stale-writer protection:

- a write carrying an older fencing token than the stored ``write_fence``
  is rejected (before V6 it silently overwrote newer state)
- same-token re-saves and higher tokens proceed; the fence advances
- ``expected_fencing_token=None`` is the documented unconditional legacy path
  and never mutates the stored fence
- the orchestrator reports a rejected stale write as ``lease_lost`` —
  never as successful persistence — in both execute and resume flows
- two independent OS processes on one SQLite file cannot regress the fence
  (process-level proof; NOT a claim about distributed databases)
"""

from __future__ import annotations

import asyncio
import dataclasses
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

import pytest

from app.domain.entities.causal_state_types import DurableExecutionStep
from app.domain.repositories.causal_state_repositories import StaleFencingTokenError

REPO_ROOT = Path(__file__).resolve().parents[2]


def _step(**overrides: Any) -> DurableExecutionStep:
    base: dict[str, Any] = dict(
        step_id="step-fence-1",
        plan_id="plan-fence-1",
        action_id="act-fence-1",
        execution_order=0,
        tenant_id="t-fence",
        execution_state="pending",
    )
    base.update(overrides)
    return DurableExecutionStep(**base)


def _make_repo(db_session: Any) -> Any:
    from app.infrastructure.persistence.repositories.sqlalchemy_causal_state_repositories import (
        SQLAlchemyDurableExecutionRepository,
    )

    return SQLAlchemyDurableExecutionRepository(db_session)


class _NoEvidenceRepo:
    """Evidence repository stub: no evidence exists for any action."""

    async def get_by_action_id(self, tenant_id: str, action_id: str) -> None:
        return None


class TestFencedWrites:
    @pytest.mark.asyncio
    async def test_stale_token_write_is_rejected(self, db_session: Any) -> None:
        repo = _make_repo(db_session)
        await repo.save(_step(), expected_fencing_token=5)
        with pytest.raises(StaleFencingTokenError):
            await repo.save(
                dataclasses.replace(_step(), execution_state="succeeded"),
                expected_fencing_token=3,
            )
        db_session.commit()

    @pytest.mark.asyncio
    async def test_stale_write_leaves_persisted_state_intact(
        self, db_session: Any
    ) -> None:
        repo = _make_repo(db_session)
        await repo.save(_step(), expected_fencing_token=5)
        with pytest.raises(StaleFencingTokenError):
            await repo.save(
                dataclasses.replace(_step(), execution_state="succeeded"),
                expected_fencing_token=3,
            )
        current = await repo.get_by_step_id("t-fence", "step-fence-1")
        assert current is not None
        assert current.execution_state == "pending", "stale writer overwrote state"
        db_session.commit()

    @pytest.mark.asyncio
    async def test_same_token_write_is_allowed(self, db_session: Any) -> None:
        repo = _make_repo(db_session)
        await repo.save(_step(), expected_fencing_token=5)
        await repo.save(
            dataclasses.replace(_step(), execution_state="running"),
            expected_fencing_token=5,
        )
        current = await repo.get_by_step_id("t-fence", "step-fence-1")
        assert current is not None
        assert current.execution_state == "running"
        db_session.commit()

    @pytest.mark.asyncio
    async def test_higher_token_write_allowed_and_advances_fence(
        self, db_session: Any
    ) -> None:
        repo = _make_repo(db_session)
        await repo.save(_step(), expected_fencing_token=5)
        await repo.save(
            dataclasses.replace(_step(), execution_state="succeeded"),
            expected_fencing_token=7,
        )
        current = await repo.get_by_step_id("t-fence", "step-fence-1")
        assert current is not None
        assert current.execution_state == "succeeded"
        assert current.write_fence == 7
        db_session.commit()

    @pytest.mark.asyncio
    async def test_none_token_is_unconditional_and_preserves_fence(
        self, db_session: Any
    ) -> None:
        # Documented legacy behavior: no token = unconditional write, and the
        # stored fence is never reset by such a write.
        repo = _make_repo(db_session)
        await repo.save(_step(), expected_fencing_token=7)
        await repo.save(
            dataclasses.replace(_step(), execution_state="running")
        )  # no token
        current = await repo.get_by_step_id("t-fence", "step-fence-1")
        assert current is not None
        assert current.execution_state == "running"
        assert current.write_fence == 7, "legacy write must not reset the fence"
        db_session.commit()

    @pytest.mark.asyncio
    async def test_insert_with_token_establishes_fence(self, db_session: Any) -> None:
        repo = _make_repo(db_session)
        await repo.save(_step(), expected_fencing_token=9)
        current = await repo.get_by_step_id("t-fence", "step-fence-1")
        assert current is not None
        assert current.write_fence == 9
        with pytest.raises(StaleFencingTokenError):
            await repo.save(
                dataclasses.replace(_step(), execution_state="succeeded"),
                expected_fencing_token=8,
            )
        db_session.commit()

    @pytest.mark.asyncio
    async def test_fresh_row_with_none_token_starts_at_zero_fence(
        self, db_session: Any
    ) -> None:
        repo = _make_repo(db_session)
        await repo.save(_step())
        current = await repo.get_by_step_id("t-fence", "step-fence-1")
        assert current is not None
        assert current.write_fence == 0
        db_session.commit()


class TestOrchestratorStaleWriteOutcome:
    @pytest.mark.asyncio
    async def test_step_write_rejection_is_lease_lost_not_success(
        self, db_session: Any
    ) -> None:
        from app.domain.services.distributed_recovery_orchestrator import (
            DistributedRecoveryOrchestrator,
        )

        repo = _make_repo(db_session)
        await repo.save(_step(), expected_fencing_token=42)  # takeover advanced fence
        orch = DistributedRecoveryOrchestrator(
            evidence_repository=_NoEvidenceRepo(),
            execution_repository=repo,
            adapters=[],
        )
        loaded = await repo.get_by_step_id("t-fence", "step-fence-1")
        assert loaded is not None

        result = await orch._execute_single_step(
            "t-fence", loaded, fencing_token=1
        )

        assert result.get("lease_lost") is True
        assert result.get("success") is False
        assert "fencing" in str(result.get("error", "")).lower()
        # The rejected write must not be reported as persisted:
        current = await repo.get_by_step_id("t-fence", "step-fence-1")
        assert current is not None
        assert current.execution_state == "pending"
        db_session.commit()

    @pytest.mark.asyncio
    async def test_plan_execution_aborts_with_lease_lost_on_stale_fence(
        self, db_session: Any
    ) -> None:
        from app.domain.services.distributed_recovery_orchestrator import (
            DistributedRecoveryOrchestrator,
            InMemoryPlanLeaseStore,
        )

        repo = _make_repo(db_session)
        await repo.save(_step())  # initial creation, fence 0
        store = InMemoryPlanLeaseStore()
        orch = DistributedRecoveryOrchestrator(
            evidence_repository=_NoEvidenceRepo(),
            execution_repository=repo,
            adapters=[],
            lease_store=store,
        )
        lease = await store.try_acquire("plan-fence-1", orch._instance_id, 300.0)
        assert lease is not None and lease.fencing_token == 1
        # Another instance advanced the durable write fence behind our back
        # (simulated takeover) while our in-memory lease is unaware of it.
        loaded = await repo.get_by_step_id("t-fence", "step-fence-1")
        assert loaded is not None
        await repo.save(loaded, expected_fencing_token=5)

        response = await orch._do_execute_durable_plan(
            "t-fence", "plan-fence-1", [], lease=lease
        )

        assert response["status"] == "lease_lost"
        assert response["completed"] == 0
        step_result = response["execution_results"]["act-fence-1"]
        assert step_result.get("lease_lost") is True
        assert step_result.get("success") is False
        current = await repo.get_by_step_id("t-fence", "step-fence-1")
        assert current is not None
        assert current.execution_state == "pending"
        db_session.commit()

    @pytest.mark.asyncio
    async def test_resume_write_rejection_is_lease_lost(
        self, db_session: Any
    ) -> None:
        from app.domain.services.distributed_recovery_orchestrator import (
            DistributedRecoveryOrchestrator,
            InMemoryPlanLeaseStore,
        )

        repo = _make_repo(db_session)
        await repo.save(_step(execution_state="failed", retry_count=0))
        store = InMemoryPlanLeaseStore()
        orch = DistributedRecoveryOrchestrator(
            evidence_repository=_NoEvidenceRepo(),
            execution_repository=repo,
            adapters=[],
            lease_store=store,
        )
        lease = await store.try_acquire("plan-fence-1", orch._instance_id, 300.0)
        assert lease is not None
        loaded = await repo.get_by_step_id("t-fence", "step-fence-1")
        assert loaded is not None
        await repo.save(loaded, expected_fencing_token=6)

        # _do_resume_plan acquires its token from the successful renewal of
        # the already-held lease (fencing token 1) — no lease parameter.
        response = await orch._do_resume_plan("t-fence", "plan-fence-1", [])

        assert response["status"] == "lease_lost"
        assert response["execution_results"]["act-fence-1"].get("lease_lost") is True
        current = await repo.get_by_step_id("t-fence", "step-fence-1")
        assert current is not None
        assert current.execution_state == "failed", "stale resume overwrote state"
        db_session.commit()


_CHILD_SCRIPT = textwrap.dedent(
    """
    import asyncio
    import sys
    import traceback

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.domain.entities.causal_state_types import DurableExecutionStep
    from app.domain.repositories.causal_state_repositories import (
        StaleFencingTokenError,
    )
    from app.infrastructure.persistence.database import Base
    from app.infrastructure.persistence.repositories.sqlalchemy_causal_state_repositories import (
        SQLAlchemyDurableExecutionRepository,
    )

    db_url, token, state = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    engine = create_engine(db_url)
    Base.metadata.create_all(engine)
    session = sessionmaker(engine)()
    repo = SQLAlchemyDurableExecutionRepository(session)
    step = DurableExecutionStep(
        step_id="step-mp-1",
        plan_id="plan-mp-1",
        action_id="act-mp-1",
        execution_order=0,
        tenant_id="t-mp",
        execution_state=state,
    )
    try:
        asyncio.run(repo.save(step, expected_fencing_token=token))
        session.commit()
        sys.exit(0)
    except StaleFencingTokenError:
        session.rollback()
        sys.exit(42)
    except Exception:
        session.rollback()
        traceback.print_exc()
        sys.exit(1)
    """
)


class TestMultiprocessFencing:
    """Two independent OS processes, one SQLite file.

    This proves the conditional write fence is enforced at the storage layer
    across process boundaries. It does NOT prove distributed-database
    correctness (SQLite only; no Postgres/Redis service is available here).
    """

    def _run_child(self, db_url: str, token: int, state: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-c", _CHILD_SCRIPT, db_url, str(token), state],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )

    def test_child_process_can_advance_fence_and_parent_cannot_regress(
        self, tmp_path: Any
    ) -> None:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from app.infrastructure.persistence.database import Base

        db_file = tmp_path / "fence.db"
        db_url = f"sqlite:///{db_file.as_posix()}"

        # Parent establishes the row at fence 1, then closes all handles so
        # the child processes own the file exclusively.
        engine = create_engine(db_url)
        Base.metadata.create_all(engine)
        parent = sessionmaker(engine)()
        parent_repo = _make_repo(parent)
        asyncio.run(parent_repo.save(_step_mp(), expected_fencing_token=1))
        parent.commit()
        parent.close()
        engine.dispose()

        # 1) Child with a NEWER token (5 > 1) must succeed across the
        #    process boundary.
        child = self._run_child(db_url, 5, "from-child")
        assert child.returncode == 0, f"child failed: {child.stdout}\n{child.stderr}"

        # 2) Parent, now stale (3 < 5), must be rejected — not silently win.
        engine2 = create_engine(db_url)
        parent2 = sessionmaker(engine2)()
        parent_repo2 = _make_repo(parent2)
        with pytest.raises(StaleFencingTokenError):
            asyncio.run(
                parent_repo2.save(
                    dataclasses.replace(_step_mp(), execution_state="stale-parent"),
                    expected_fencing_token=3,
                )
            )
        parent2.rollback()
        parent2.close()
        engine2.dispose()

        # 3) Parent re-establishes authority at 9; a child at 7 must be
        #    rejected inside its own process (exit 42).
        engine3 = create_engine(db_url)
        parent3 = sessionmaker(engine3)()
        parent_repo3 = _make_repo(parent3)
        asyncio.run(parent_repo3.save(_step_mp_state("parent-9"), expected_fencing_token=9))
        parent3.commit()
        parent3.close()
        engine3.dispose()

        child2 = self._run_child(db_url, 7, "stale-child")
        assert child2.returncode == 42, (
            f"stale child was not rejected: rc={child2.returncode}\n"
            f"{child2.stdout}\n{child2.stderr}"
        )

        # Final state must be the newest writer's ("parent-9").
        engine4 = create_engine(db_url)
        final_repo = _make_repo(sessionmaker(engine4)())
        final = asyncio.run(final_repo.get_by_step_id("t-mp", "step-mp-1"))
        assert final is not None
        assert final.execution_state == "parent-9"
        assert final.write_fence == 9
        engine4.dispose()


def _step_mp() -> DurableExecutionStep:
    return DurableExecutionStep(
        step_id="step-mp-1",
        plan_id="plan-mp-1",
        action_id="act-mp-1",
        execution_order=0,
        tenant_id="t-mp",
        execution_state="pending",
    )


def _step_mp_state(state: str) -> DurableExecutionStep:
    return dataclasses.replace(_step_mp(), execution_state=state)
