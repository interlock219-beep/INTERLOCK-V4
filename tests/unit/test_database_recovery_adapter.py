"""Tests for production-grade database recovery adapter."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.domain.entities.protected_action import ActionStatus, ProtectedAction, Reversibility
from app.domain.entities.surgical_recovery_types import ExecutionState
from app.infrastructure.recovery.database_recovery_adapter import DatabaseRecoveryAdapter


def _make_db_action(
    action_id: str = "act-db-1",
    action_type: str = "update",
    resource: str = "table:users",
    reversibility: Reversibility = Reversibility.AUTOMATICALLY_REVERSIBLE,
    before_state_ref: str | None = "state:before:123",
    tool: str = "database",
    tool_arguments: dict | None = None,
) -> ProtectedAction:
    return ProtectedAction(
        action_id=action_id,
        tenant_id="test-tenant",
        agent_id="agent-test",
        actor_user_id=None,
        authority_grant_id=None,
        tool=tool,
        resource=resource,
        action_type=action_type,
        risk_score=0.5,
        policy_version="v1",
        correlation_id="corr-1",
        parent_action_id=None,
        workflow_id=None,
        reversibility=reversibility,
        before_state_ref=before_state_ref,
        after_state_ref="state:after:456",
        tool_arguments=tool_arguments or {"table": "users", "primary_key": "id"},
        status=ActionStatus.EXECUTED,
        decision_reason="test",
        evaluated_at=None,
        executed_at=None,
        created_at=None,
    )


def _create_test_db(db_path: Path) -> None:
    """Create a test SQLite database with sample data."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user'
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            product TEXT NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1
        )
    """)
    conn.execute(
        "INSERT INTO users (username, email, role) VALUES (?, ?, ?)",
        ("alice", "alice@example.com", "admin"),
    )
    conn.execute(
        "INSERT INTO users (username, email, role) VALUES (?, ?, ?)",
        ("bob", "bob@example.com", "user"),
    )
    conn.execute(
        "INSERT INTO orders (user_id, product, quantity) VALUES (?, ?, ?)",
        (1, "Widget", 2),
    )
    conn.commit()
    conn.close()


class TestDatabaseRecoveryAdapterDeclareCapabilities:
    """Test capability declaration."""

    @pytest.mark.asyncio
    async def test_declare_capabilities(self) -> None:
        adapter = DatabaseRecoveryAdapter()
        caps = await adapter.declare_capabilities()
        assert caps.adapter_name == "database_recovery"
        assert caps.can_capture_before_state is True
        assert caps.can_compensate is True
        assert caps.can_verify is True
        assert "transaction_safe" in caps.declared_capabilities


class TestDatabaseRecoveryAdapterCanRecover:
    """Test can_recover classification."""

    @pytest.mark.asyncio
    async def test_can_recover_update(self) -> None:
        adapter = DatabaseRecoveryAdapter()
        action = _make_db_action(action_type="update", before_state_ref="state:abc")
        result = await adapter.can_recover(action)
        assert result == "automatically_reversible"

    @pytest.mark.asyncio
    async def test_can_recover_irreversible(self) -> None:
        adapter = DatabaseRecoveryAdapter()
        action = _make_db_action(reversibility=Reversibility.IRREVERSIBLE)
        result = await adapter.can_recover(action)
        assert result == "irreversible"

    @pytest.mark.asyncio
    async def test_can_recover_unsupported(self) -> None:
        adapter = DatabaseRecoveryAdapter()
        action = _make_db_action(tool="email", action_type="send")
        result = await adapter.can_recover(action)
        assert result == "unsupported"


class TestDatabaseRecoveryAdapterInsertRecovery:
    """Test INSERT recovery (delete the inserted row)."""

    @pytest.mark.asyncio
    async def test_insert_recovery(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        _create_test_db(db_path)

        adapter = DatabaseRecoveryAdapter(db_path=db_path)

        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "INSERT INTO users (username, email, role) VALUES (?, ?, ?)",
            ("newuser", "new@example.com", "user"),
        )
        conn.commit()

        cursor = conn.execute("SELECT * FROM users WHERE username = ?", ("newuser",))
        assert cursor.fetchone() is not None
        conn.close()

        action = _make_db_action(
            action_id="act-insert-1",
            action_type="insert",
            resource="table:users",
            tool_arguments={
                "table": "users",
                "primary_key": "id",
                "row_data": {
                    "id": 3,
                    "username": "newuser",
                    "email": "new@example.com",
                    "role": "user",
                },
            },
        )

        evidence = await adapter.capture_recovery_evidence(action, {"db_path": str(db_path)})
        compensation = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(compensation, evidence.idempotency_key)

        assert result.success is True
        assert result.execution_state == ExecutionState.SUCCEEDED

        verification = await adapter.verify(compensation)
        assert verification.verified is True

        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("SELECT * FROM users WHERE username = ?", ("newuser",))
        assert cursor.fetchone() is None
        conn.close()


class TestDatabaseRecoveryAdapterUpdateRecovery:
    """Test UPDATE recovery (restore previous values)."""

    @pytest.mark.asyncio
    async def test_update_recovery(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        _create_test_db(db_path)

        adapter = DatabaseRecoveryAdapter(db_path=db_path)

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM users WHERE id = ?", (1,))
        original_row = dict(cursor.fetchone())
        conn.close()

        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "UPDATE users SET email = ?, role = ? WHERE id = ?",
            ("changed@example.com", "user", 1),
        )
        conn.commit()
        conn.close()

        action = _make_db_action(
            action_id="act-update-1",
            action_type="update",
            resource="table:users",
            tool_arguments={
                "table": "users",
                "primary_key": "id",
                "row_data": {
                    "id": 1,
                    "username": "alice",
                    "email": "changed@example.com",
                    "role": "user",
                },
            },
        )

        evidence = await adapter.capture_recovery_evidence(action, {"db_path": str(db_path)})

        evidence.compensation_payload["before_state"] = {
            "hash": "original_hash",
            "row_data": original_row,
            "row_count": 1,
        }

        compensation = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(compensation, evidence.idempotency_key)

        assert result.success is True
        assert result.execution_state == ExecutionState.SUCCEEDED

        verification = await adapter.verify(compensation)
        assert verification.verified is True

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM users WHERE id = ?", (1,))
        row = cursor.fetchone()
        assert row["email"] == original_row["email"]
        assert row["role"] == original_row["role"]
        conn.close()

    @pytest.mark.asyncio
    async def test_update_conflict_blocks_recovery(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        _create_test_db(db_path)

        adapter = DatabaseRecoveryAdapter(db_path=db_path)

        action = _make_db_action(
            action_id="act-update-conflict",
            action_type="update",
            resource="table:users",
            tool_arguments={
                "table": "users",
                "primary_key": "id",
                "row_data": {
                    "id": 1,
                    "username": "alice",
                    "email": "alice@example.com",
                    "role": "admin",
                },
            },
        )

        evidence = await adapter.capture_recovery_evidence(action, {"db_path": str(db_path)})

        conn = sqlite3.connect(str(db_path))
        conn.execute("UPDATE users SET email = ? WHERE id = ?", ("agent@evil.com", 1))
        conn.commit()
        conn.execute("UPDATE users SET email = ? WHERE id = ?", ("human@legit.com", 1))
        conn.commit()
        conn.close()

        compensation = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(compensation, evidence.idempotency_key)

        assert result.success is False
        assert result.execution_state == ExecutionState.BLOCKED_BY_CONFLICT

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM users WHERE id = ?", (1,))
        row = cursor.fetchone()
        assert row["email"] == "human@legit.com"
        conn.close()


class TestDatabaseRecoveryAdapterDeleteRecovery:
    """Test DELETE recovery (re-insert the deleted row)."""

    @pytest.mark.asyncio
    async def test_delete_recovery(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        _create_test_db(db_path)

        adapter = DatabaseRecoveryAdapter(db_path=db_path)

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM users WHERE id = ?", (2,))
        original_row = dict(cursor.fetchone())
        conn.close()

        action = _make_db_action(
            action_id="act-delete-1",
            action_type="delete",
            resource="table:users",
            tool_arguments={
                "table": "users",
                "primary_key": "id",
                "row_data": {
                    "id": 2,
                    "username": "bob",
                    "email": "bob@example.com",
                    "role": "user",
                },
            },
        )

        evidence = await adapter.capture_recovery_evidence(action, {"db_path": str(db_path)})

        evidence.compensation_payload["before_state"] = {
            "hash": "original_hash",
            "row_data": original_row,
            "row_count": 1,
        }

        conn = sqlite3.connect(str(db_path))
        conn.execute("DELETE FROM users WHERE id = ?", (2,))
        conn.commit()
        conn.close()

        compensation = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(compensation, evidence.idempotency_key)

        assert result.success is True
        assert result.execution_state == ExecutionState.SUCCEEDED

        verification = await adapter.verify(compensation)
        assert verification.verified is True

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM users WHERE id = ?", (2,))
        row = cursor.fetchone()
        assert row is not None
        assert row["username"] == original_row["username"]
        assert row["email"] == original_row["email"]
        conn.close()


class TestDatabaseRecoveryAdapterSecurity:
    """Adversarial tests for SQL injection resistance."""

    @pytest.mark.asyncio
    async def test_malicious_table_name_in_resource_rejected(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        _create_test_db(db_path)
        adapter = DatabaseRecoveryAdapter(db_path=db_path)

        action = _make_db_action(
            action_id="act-mal-table",
            action_type="insert",
            resource="table:users; DROP TABLE users; --",
            tool_arguments={
                "primary_key": "id",
                "row_data": {
                    "id": 99,
                    "username": "evil",
                    "email": "evil@test.com",
                    "role": "user",
                },
            },
        )

        evidence = await adapter.capture_recovery_evidence(action, {"db_path": str(db_path)})
        compensation = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(compensation, evidence.idempotency_key)

        assert result.success is False
        assert result.execution_state == ExecutionState.FAILED

        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        assert cursor.fetchone() is not None
        conn.close()

    @pytest.mark.asyncio
    async def test_malicious_primary_key_falls_back_to_id(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        _create_test_db(db_path)
        adapter = DatabaseRecoveryAdapter(db_path=db_path)

        action = _make_db_action(
            action_id="act-mal-pk",
            action_type="update",
            resource="table:users",
            tool_arguments={
                "primary_key": "id; DROP TABLE users; --",
                "row_data": {
                    "id": 1,
                    "username": "alice",
                    "email": "alice@example.com",
                    "role": "user",
                },
            },
        )

        evidence = await adapter.capture_recovery_evidence(action, {"db_path": str(db_path)})
        compensation = await adapter.generate_compensation(action, evidence)

        payload = compensation.compensation_payload
        assert payload.get("primary_key") == "id"

        evidence.compensation_payload["before_state"] = {
            "hash": "original_hash",
            "row_data": {
                "id": 1,
                "username": "alice",
                "email": "alice@example.com",
                "role": "admin",
            },
            "row_count": 1,
        }

        result = await adapter.execute_compensation(compensation, evidence.idempotency_key)
        assert result.success is True
        assert result.execution_state == ExecutionState.SUCCEEDED

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM users WHERE id = ?", (1,))
        row = cursor.fetchone()
        assert row is not None
        assert row["role"] == "admin"
        conn.close()

    @pytest.mark.asyncio
    async def test_sql_injection_in_values_stays_quoted(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        _create_test_db(db_path)

        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "INSERT INTO users (id, username, email, role) VALUES (?, ?, ?, ?)",
            (99, "evil", "evil@test.com' OR '1'='1", "user"),
        )
        conn.commit()
        cursor = conn.execute("SELECT * FROM users WHERE id = ?", (99,))
        assert cursor.fetchone() is not None
        conn.close()

        adapter = DatabaseRecoveryAdapter(db_path=db_path)
        action = _make_db_action(
            action_id="act-mal-val",
            action_type="insert",
            resource="table:users",
            tool_arguments={
                "primary_key": "id",
                "row_data": {
                    "id": 99,
                    "username": "evil",
                    "email": "evil@test.com' OR '1'='1",
                    "role": "user",
                },
            },
        )

        evidence = await adapter.capture_recovery_evidence(action, {"db_path": str(db_path)})
        compensation = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(compensation, evidence.idempotency_key)

        assert result.success is True
        assert result.execution_state == ExecutionState.SUCCEEDED

        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("SELECT * FROM users WHERE id = ?", (99,))
        assert cursor.fetchone() is None
        conn.close()

    @pytest.mark.asyncio
    async def test_sql_keyword_as_table_name_rejected(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        _create_test_db(db_path)
        adapter = DatabaseRecoveryAdapter(db_path=db_path)

        for keyword in ("SELECT", "DROP", "DELETE", "UPDATE", "INSERT", "WHERE"):
            action = _make_db_action(
                action_id=f"act-mal-{keyword.lower()}",
                action_type="insert",
                resource=f"table:{keyword}",
                tool_arguments={
                    "primary_key": "id",
                    "row_data": {"id": 99, "username": "x", "email": "x@test.com", "role": "user"},
                },
            )

            evidence = await adapter.capture_recovery_evidence(action, {"db_path": str(db_path)})
            compensation = await adapter.generate_compensation(action, evidence)
            result = await adapter.execute_compensation(compensation, evidence.idempotency_key)

            assert result.success is False
            assert result.execution_state == ExecutionState.FAILED

    @pytest.mark.asyncio
    async def test_empty_and_numeric_identifiers_rejected(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        _create_test_db(db_path)
        adapter = DatabaseRecoveryAdapter(db_path=db_path)

        for bad_table in ("", "123", "users-evil"):
            action = _make_db_action(
                action_id=f"act-bad-{hash(bad_table)}",
                action_type="insert",
                resource=f"table:{bad_table}",
                tool_arguments={
                    "primary_key": "id",
                    "row_data": {"id": 99, "username": "x", "email": "x@test.com", "role": "user"},
                },
            )

            evidence = await adapter.capture_recovery_evidence(action, {"db_path": str(db_path)})
            compensation = await adapter.generate_compensation(action, evidence)
            result = await adapter.execute_compensation(compensation, evidence.idempotency_key)

            assert result.success is False
            assert result.execution_state == ExecutionState.FAILED

    @pytest.mark.asyncio
    async def test_malicious_column_name_in_update_skipped(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        _create_test_db(db_path)
        adapter = DatabaseRecoveryAdapter(db_path=db_path)

        action = _make_db_action(
            action_id="act-mal-update-col",
            action_type="update",
            resource="table:users",
            tool_arguments={
                "primary_key": "id",
                "row_data": {
                    "id": 1,
                    "username": "alice",
                    "email": "alice@example.com",
                    "role": "user",
                    "evil; DROP TABLE users; --": "hacked",
                },
            },
        )

        evidence = await adapter.capture_recovery_evidence(action, {"db_path": str(db_path)})
        evidence.compensation_payload["before_state"] = {
            "hash": "original_hash",
            "row_data": {
                "id": 1,
                "username": "alice",
                "email": "alice@example.com",
                "role": "admin",
            },
            "row_count": 1,
        }

        compensation = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(compensation, evidence.idempotency_key)

        assert result.success is True
        assert result.execution_state == ExecutionState.SUCCEEDED

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM users WHERE id = ?", (1,))
        row = cursor.fetchone()
        assert row is not None
        assert row["email"] == "alice@example.com"
        assert row["role"] == "admin"
        conn.close()


class TestDatabaseRecoveryAdapterEndToEnd:
    """End-to-end database recovery scenarios."""

    @pytest.mark.asyncio
    async def test_full_update_recovery_workflow(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        _create_test_db(db_path)

        adapter = DatabaseRecoveryAdapter(db_path=db_path)

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM users WHERE id = ?", (1,))
        original_row = dict(cursor.fetchone())
        conn.close()

        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "UPDATE users SET email = ?, role = ? WHERE id = ?",
            ("hacked@evil.com", "user", 1),
        )
        conn.commit()
        conn.close()

        action = _make_db_action(
            action_id="act-e2e-db",
            action_type="update",
            resource="table:users",
            tool_arguments={
                "table": "users",
                "primary_key": "id",
                "row_data": {
                    "id": 1,
                    "username": "alice",
                    "email": "hacked@evil.com",
                    "role": "user",
                },
            },
        )

        evidence = await adapter.capture_recovery_evidence(action, {"db_path": str(db_path)})

        evidence.compensation_payload["before_state"] = {
            "hash": "original_hash",
            "row_data": original_row,
            "row_count": 1,
        }

        impact = await adapter.simulate(action, evidence)
        assert impact.would_succeed is True

        compensation = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(compensation, evidence.idempotency_key)
        assert result.success is True

        verification = await adapter.verify(compensation)
        assert verification.verified is True

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM users WHERE id = ?", (1,))
        row = cursor.fetchone()
        assert row["email"] == original_row["email"]
        assert row["role"] == original_row["role"]
        conn.close()

    @pytest.mark.asyncio
    async def test_multiple_operations_recovery(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        _create_test_db(db_path)

        adapter = DatabaseRecoveryAdapter(db_path=db_path)

        action1 = _make_db_action(
            action_id="act-multi-insert",
            action_type="insert",
            resource="table:users",
            tool_arguments={
                "table": "users",
                "primary_key": "id",
                "row_data": {
                    "id": 3,
                    "username": "mallory",
                    "email": "mallory@evil.com",
                    "role": "user",
                },
            },
        )

        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "INSERT INTO users (username, email, role) VALUES (?, ?, ?)",
            ("mallory", "mallory@evil.com", "user"),
        )
        conn.commit()
        conn.close()

        evidence1 = await adapter.capture_recovery_evidence(action1, {"db_path": str(db_path)})
        comp1 = await adapter.generate_compensation(action1, evidence1)
        result1 = await adapter.execute_compensation(comp1, evidence1.idempotency_key)

        assert result1.success is True

        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("SELECT * FROM users WHERE username = ?", ("mallory",))
        assert cursor.fetchone() is None
        conn.close()
