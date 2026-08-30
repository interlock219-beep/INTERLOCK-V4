"""Disposable test environment for recovery validation.

Provides isolated, reproducible environments containing:
- Temporary filesystem
- SQLite database
- Git repository
- Configuration state
- Simulated external API
- Simulated infrastructure resources

All resources are automatically cleaned up after tests.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest


class DisposableEnvironment:
    """Isolated disposable test environment.

    All state is contained within a temporary directory that is
    automatically cleaned up on deletion.
    """

    def __init__(self) -> None:
        self._temp_dir = tempfile.mkdtemp(prefix="interlock_recovery_lab_")
        self.root = Path(self._temp_dir)
        self.filesystem = FilesystemResource(self.root / "filesystem")
        self.database = DatabaseResource(self.root / "database.db")
        self.git_repo = GitResource(self.root / "git_repo")
        self.config = ConfigResource(self.root / "config")
        self.external_api = MockExternalAPI(self.root / "external_api.json")
        self.infrastructure = InfrastructureResource(self.root / "infrastructure")

        # Create directories
        self.filesystem.path.mkdir(parents=True, exist_ok=True)
        self.config.path.mkdir(parents=True, exist_ok=True)
        self.infrastructure.path.mkdir(parents=True, exist_ok=True)

        # Initialize components
        self._initialize()

    def _initialize(self) -> None:
        """Initialize all resources to a known-good state."""
        # Initialize filesystem with baseline files
        self.filesystem.write("readme.txt", "Hello, World!")
        self.filesystem.write("config/app.yaml", "app:\n  name: test-app\n  version: 1.0.0\n")
        self.filesystem.write("data/sample.txt", "sample data content")

        # Initialize database with baseline tables and data
        self.database.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                created_at TEXT NOT NULL
            )
        """)
        self.database.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                product TEXT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL
            )
        """)
        self.database.execute("""
            INSERT INTO users (username, email, role, created_at)
            VALUES (?, ?, ?, ?)
        """, ("alice", "alice@example.com", "admin", datetime.now(UTC).isoformat()))
        self.database.execute("""
            INSERT INTO users (username, email, role, created_at)
            VALUES (?, ?, ?, ?)
        """, ("bob", "bob@example.com", "user", datetime.now(UTC).isoformat()))
        self.database.execute("""
            INSERT INTO orders (user_id, product, quantity, status, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (1, "Widget", 2, "pending", datetime.now(UTC).isoformat()))

        # Initialize git repository
        self.git_repo.initialize()
        self.git_repo.add_file("readme.txt", "Hello, World!")
        self.git_repo.commit("Initial commit")

        # Initialize config
        self.config.write("settings.json", json.dumps({
            "app_name": "test-app",
            "version": "1.0.0",
            "debug": False,
            "max_connections": 100,
        }))

        # Initialize external API state
        self.external_api.write_state({
            "endpoints": {
                "/api/users": {"method": "GET", "status": "active"},
                "/api/orders": {"method": "POST", "status": "active"},
            },
            "rate_limits": {"default": 100, "premium": 1000},
        })

        # Initialize infrastructure state
        self.infrastructure.write_state({
            "resources": [
                {"id": "res-1", "type": "compute", "name": "web-server-1", "status": "running"},
                {"id": "res-2", "type": "storage", "name": "db-storage-1", "status": "active"},
            ],
            "networks": [
                {"id": "net-1", "name": "public-net", "cidr": "10.0.0.0/16"},
            ],
        })

    def compute_fingerprint(self) -> str:
        """Compute a deterministic fingerprint of the entire environment state."""
        fingerprint_data = {
            "files": self.filesystem.fingerprint(),
            "database": self.database.fingerprint(),
            "git": self.git_repo.fingerprint(),
            "config": self.config.fingerprint(),
            "external_api": self.external_api.fingerprint(),
            "infrastructure": self.infrastructure.fingerprint(),
        }
        fingerprint_str = json.dumps(fingerprint_data, sort_keys=True)
        return hashlib.sha256(fingerprint_str.encode()).hexdigest()

    def verify_restored(self, baseline_fingerprint: str) -> dict[str, Any]:
        """Verify that the environment has been restored to the baseline state.

        Returns a detailed verification report.
        """
        current_fingerprint = self.compute_fingerprint()
        fingerprint_match = current_fingerprint == baseline_fingerprint

        files_ok = self.filesystem.verify()
        database_ok = self.database.verify()
        git_ok = self.git_repo.verify()
        config_ok = self.config.verify()
        external_ok = self.external_api.verify()
        infra_ok = self.infrastructure.verify()

        all_ok = all([files_ok, database_ok, git_ok, config_ok, external_ok, infra_ok])

        return {
            "fingerprint_match": fingerprint_match,
            "baseline_fingerprint": baseline_fingerprint,
            "current_fingerprint": current_fingerprint,
            "resources": {
                "filesystem": files_ok,
                "database": database_ok,
                "git": git_ok,
                "config": config_ok,
                "external_api": external_ok,
                "infrastructure": infra_ok,
            },
            "fully_restored": all_ok and fingerprint_match,
            "verification_method": "independent_external_state_verification",
        }

    def cleanup(self) -> None:
        """Remove all temporary resources."""
        import shutil
        if self._temp_dir and Path(self._temp_dir).exists():
            shutil.rmtree(self._temp_dir, ignore_errors=True)

    def __enter__(self) -> DisposableEnvironment:
        return self

    def __exit__(self, *args: Any) -> None:
        self.cleanup()


class FilesystemResource:
    """Manages a temporary filesystem for testing."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._baseline: dict[str, str] = {}

    def write(self, relative_path: str, content: str) -> Path:
        file_path = self.path / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return file_path

    def read(self, relative_path: str) -> str:
        return (self.path / relative_path).read_text(encoding="utf-8")

    def delete(self, relative_path: str) -> None:
        (self.path / relative_path).unlink(missing_ok=True)

    def rename(self, old_path: str, new_path: str) -> None:
        (self.path / old_path).rename(self.path / new_path)

    def list_files(self) -> list[str]:
        return [
            str(f.relative_to(self.path))
            for f in self.path.rglob("*")
            if f.is_file()
        ]

    def fingerprint(self) -> dict[str, str]:
        result = {}
        for file_path in self.list_files():
            try:
                content = self.read(file_path)
                result[file_path] = hashlib.sha256(content.encode()).hexdigest()
            except Exception:
                result[file_path] = "missing"
        return result

    def verify(self) -> bool:
        """Verify all expected baseline files exist with correct content."""
        for rel_path, expected_hash in self._baseline.items():
            try:
                content = self.read(rel_path)
                actual_hash = hashlib.sha256(content.encode()).hexdigest()
                if actual_hash != expected_hash:
                    return False
            except Exception:
                return False
        return True

    def capture_baseline(self) -> None:
        self._baseline = {
            rel_path: hashlib.sha256(self.read(rel_path).encode()).hexdigest()
            for rel_path in self.list_files()
        }


class DatabaseResource:
    """Manages a temporary SQLite database for testing."""

    def __init__(self, db_path: str | Path) -> None:
        self.path = Path(db_path)
        self._conn: sqlite3.Connection | None = None
        self._baseline: dict[str, Any] = {}

    def connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> Any:
        conn = self.connect()
        return conn.execute(sql, params)

    def fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        cursor = self.execute(sql, params)
        row = cursor.fetchone()
        return dict(row) if row else None

    def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        cursor = self.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]

    def fingerprint(self) -> dict[str, Any]:
        tables = self.fetch_all(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        result = {"tables": {}}
        for table in tables:
            table_name = table["name"]
            # table_name originates from sqlite_master query results, not user input
            rows = self.fetch_all(f"SELECT * FROM {table_name}")  # noqa: S608
            result["tables"][table_name] = {
                "count": len(rows),
                "rows": [dict(r) for r in rows],
            }
        return result

    def verify(self) -> bool:
        try:
            current = self.fingerprint()
            return current == self._baseline
        except Exception:
            return False

    def capture_baseline(self) -> None:
        self._baseline = self.fingerprint()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None


class GitResource:
    """Manages a temporary git repository for testing."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._baseline_commit: str | None = None

    def initialize(self) -> None:
        self.path.mkdir(parents=True, exist_ok=True)
        self._run_git("init")
        self._run_git("config", "user.email", "test@example.com")
        self._run_git("config", "user.name", "Test User")

    def add_file(self, filename: str, content: str) -> None:
        file_path = self.path / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        self._run_git("add", filename)

    def commit(self, message: str) -> str:
        self._run_git("commit", "-m", message)
        result = self._run_git("rev-parse", "HEAD")
        return result.strip()

    def modify_file(self, filename: str, content: str) -> None:
        file_path = self.path / filename
        file_path.write_text(content, encoding="utf-8")

    def delete_file(self, filename: str) -> None:
        (self.path / filename).unlink(missing_ok=True)

    def log(self) -> list[dict[str, str]]:
        result = self._run_git(
            "log", "--pretty=format:%H|%s|%an|%ae", "--all"
        )
        commits = []
        for line in result.strip().split("\n"):
            if line:
                parts = line.split("|")
                commits.append({
                    "hash": parts[0],
                    "message": parts[1] if len(parts) > 1 else "",
                    "author": parts[2] if len(parts) > 2 else "",
                    "email": parts[3] if len(parts) > 3 else "",
                })
        return commits

    def fingerprint(self) -> str:
        try:
            result = self._run_git("rev-parse", "HEAD")
            return result.strip()
        except Exception:
            return "no_commits"

    def verify(self) -> bool:
        try:
            current = self.fingerprint()
            return current == self._baseline_commit
        except Exception:
            return False

    def capture_baseline(self) -> None:
        self._baseline_commit = self.fingerprint()

    def _run_git(self, *args: str) -> str:
        import subprocess
        # Test helper invoking the git CLI within an isolated temp directory
        result = subprocess.run(  # noqa: S603
            ["git"] + list(args),
            cwd=self.path,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"git failed: {result.stderr}")
        return result.stdout


class ConfigResource:
    """Manages configuration files for testing."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._baseline: dict[str, Any] = {}

    def write(self, filename: str, content: str) -> Path:
        file_path = self.path / filename
        file_path.write_text(content, encoding="utf-8")
        return file_path

    def read(self, filename: str) -> str:
        return (self.path / filename).read_text(encoding="utf-8")

    def read_json(self, filename: str) -> dict[str, Any]:
        return json.loads(self.read(filename))

    def write_json(self, filename: str, data: dict[str, Any]) -> Path:
        return self.write(filename, json.dumps(data, indent=2, sort_keys=True))

    def fingerprint(self) -> dict[str, str]:
        result = {}
        for f in self.path.glob("*"):
            if f.is_file():
                result[f.name] = hashlib.sha256(f.read_bytes()).hexdigest()
        return result

    def verify(self) -> bool:
        try:
            current = self.fingerprint()
            return current == self._baseline
        except Exception:
            return False

    def capture_baseline(self) -> None:
        self._baseline = self.fingerprint()


class MockExternalAPI:
    """Simulates an external API for testing."""

    def __init__(self, state_file: Path) -> None:
        self.state_file = state_file
        self._state: dict[str, Any] = {}
        self._baseline: dict[str, Any] = {}

    def write_state(self, state: dict[str, Any]) -> None:
        self._state = state
        self.state_file.write_text(json.dumps(state, indent=2, sort_keys=True))

    def read_state(self) -> dict[str, Any]:
        return json.loads(self.state_file.read_text())

    def call_endpoint(
        self, endpoint: str, method: str, data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Simulate an API call."""
        state = self.read_state()
        endpoints = state.get("endpoints", {})
        if endpoint not in endpoints:
            return {"status": "error", "code": 404, "message": "Not found"}

        endpoint_config = endpoints[endpoint]
        if method != endpoint_config.get("method", "GET"):
            return {"status": "error", "code": 405, "message": "Method not allowed"}

        return {
            "status": "success",
            "endpoint": endpoint,
            "method": method,
            "data": data,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def fingerprint(self) -> str:
        return hashlib.sha256(self.state_file.read_bytes()).hexdigest()

    def verify(self) -> bool:
        try:
            current = self.fingerprint()
            return current == self._baseline
        except Exception:
            return False

    def capture_baseline(self) -> None:
        self._baseline = self.fingerprint()


class InfrastructureResource:
    """Manages simulated infrastructure resources for testing."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._state_file = path / "state.json"
        self._baseline: dict[str, Any] = {}

    def write_state(self, state: dict[str, Any]) -> None:
        self._state_file.write_text(json.dumps(state, indent=2, sort_keys=True))

    def read_state(self) -> dict[str, Any]:
        return json.loads(self._state_file.read_text())

    def create_resource(self, resource_type: str, name: str, **kwargs: Any) -> dict[str, Any]:
        state = self.read_state()
        resources = state.get("resources", [])
        new_resource = {
            "id": f"res-{uuid4().hex[:8]}",
            "type": resource_type,
            "name": name,
            "status": "provisioned",
            "created_at": datetime.now(UTC).isoformat(),
            **kwargs,
        }
        resources.append(new_resource)
        state["resources"] = resources
        self.write_state(state)
        return new_resource

    def delete_resource(self, resource_id: str) -> bool:
        state = self.read_state()
        resources = state.get("resources", [])
        new_resources = [r for r in resources if r["id"] != resource_id]
        if len(new_resources) == len(resources):
            return False
        state["resources"] = new_resources
        self.write_state(state)
        return True

    def update_resource(self, resource_id: str, **updates: Any) -> dict[str, Any] | None:
        state = self.read_state()
        resources = state.get("resources", [])
        for resource in resources:
            if resource["id"] == resource_id:
                resource.update(updates)
                resource["updated_at"] = datetime.now(UTC).isoformat()
                self.write_state(state)
                return resource
        return None

    def fingerprint(self) -> str:
        return hashlib.sha256(self._state_file.read_bytes()).hexdigest()

    def verify(self) -> bool:
        try:
            current = self.fingerprint()
            return current == self._baseline
        except Exception:
            return False

    def capture_baseline(self) -> None:
        self._baseline = self.fingerprint()


@pytest.fixture
def recovery_lab() -> Generator[DisposableEnvironment, None, None]:
    """Provide a disposable test environment for recovery testing."""
    env = DisposableEnvironment()
    try:
        yield env
    finally:
        env.cleanup()


@pytest.fixture
def baseline_environment(recovery_lab: DisposableEnvironment) -> DisposableEnvironment:
    """Provide a disposable environment with captured baseline fingerprint."""
    recovery_lab.filesystem.capture_baseline()
    recovery_lab.database.capture_baseline()
    recovery_lab.git_repo.capture_baseline()
    recovery_lab.config.capture_baseline()
    recovery_lab.external_api.capture_baseline()
    recovery_lab.infrastructure.capture_baseline()
    return recovery_lab
