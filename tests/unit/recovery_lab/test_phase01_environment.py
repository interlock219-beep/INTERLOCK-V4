"""Phase 1 — Recovery Test Lab Environment Validation.

Validates that the disposable test environment is correctly initialized,
deterministic, and provides all required resource types for recovery testing.
"""

from __future__ import annotations

from datetime import UTC, datetime

from tests.unit.recovery_lab.environment import (
    DisposableEnvironment,
)


def _normalize_paths(paths: list[str]) -> list[str]:
    """Normalize path separators for cross-platform comparison."""
    return [p.replace("\\", "/") for p in paths]


class TestDisposableEnvironmentInitialization:
    """Verify the disposable environment initializes all resources correctly."""

    def test_environment_creates_all_resources(self) -> None:
        with DisposableEnvironment() as env:
            assert env.filesystem is not None
            assert env.database is not None
            assert env.git_repo is not None
            assert env.config is not None
            assert env.external_api is not None
            assert env.infrastructure is not None

    def test_filesystem_has_baseline_files(self) -> None:
        with DisposableEnvironment() as env:
            files = _normalize_paths(env.filesystem.list_files())
            assert "readme.txt" in files
            assert "config/app.yaml" in files
            assert "data/sample.txt" in files

    def test_database_has_baseline_tables_and_data(self) -> None:
        with DisposableEnvironment() as env:
            users = env.database.fetch_all("SELECT * FROM users")
            assert len(users) == 2
            usernames = {u["username"] for u in users}
            assert "alice" in usernames
            assert "bob" in usernames

            orders = env.database.fetch_all("SELECT * FROM orders")
            assert len(orders) == 1
            assert orders[0]["product"] == "Widget"

    def test_git_repo_initialized_with_initial_commit(self) -> None:
        with DisposableEnvironment() as env:
            log = env.git_repo.log()
            assert len(log) >= 1
            assert "Initial commit" in log[0]["message"]

    def test_config_has_baseline_settings(self) -> None:
        with DisposableEnvironment() as env:
            settings = env.config.read_json("settings.json")
            assert settings["app_name"] == "test-app"
            assert settings["version"] == "1.0.0"
            assert settings["debug"] is False

    def test_external_api_has_baseline_state(self) -> None:
        with DisposableEnvironment() as env:
            state = env.external_api.read_state()
            assert "/api/users" in state["endpoints"]
            assert "/api/orders" in state["endpoints"]

    def test_infrastructure_has_baseline_resources(self) -> None:
        with DisposableEnvironment() as env:
            state = env.infrastructure.read_state()
            assert len(state["resources"]) == 2
            assert len(state["networks"]) == 1


class TestEnvironmentDeterminism:
    """Verify that environment state is deterministic and repeatable."""

    def test_fingerprint_is_deterministic_for_same_state(self) -> None:
        with DisposableEnvironment() as env:
            fp1 = env.compute_fingerprint()
            fp2 = env.compute_fingerprint()
            assert fp1 == fp2

    def test_fingerprint_changes_after_mutation(self) -> None:
        with DisposableEnvironment() as env:
            fp_before = env.compute_fingerprint()
            env.filesystem.write("new_file.txt", "new content")
            fp_after = env.compute_fingerprint()
            assert fp_before != fp_after

    def test_two_environments_have_same_structure(self) -> None:
        """Two environments should have the same structure (tables, files, config)."""
        with DisposableEnvironment() as env1, DisposableEnvironment() as env2:
            files1 = sorted(_normalize_paths(env1.filesystem.list_files()))
            files2 = sorted(_normalize_paths(env2.filesystem.list_files()))
            assert files1 == files2

            tables1 = env1.database.fetch_all(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
            tables2 = env2.database.fetch_all(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
            assert [t["name"] for t in tables1] == [t["name"] for t in tables2]


class TestBaselineCapture:
    """Verify baseline capture and restoration verification."""

    def test_capture_and_verify_filesystem(self) -> None:
        with DisposableEnvironment() as env:
            env.filesystem.capture_baseline()
            assert env.filesystem.verify() is True

            env.filesystem.write("extra.txt", "extra")

            assert env.filesystem.verify() is True

    def test_capture_and_verify_database(self) -> None:
        with DisposableEnvironment() as env:
            env.database.capture_baseline()
            assert env.database.verify() is True

            env.database.execute(
                "INSERT INTO users (username, email, role, created_at) VALUES (?, ?, ?, ?)",
                ("charlie", "charlie@example.com", "user", datetime.now(UTC).isoformat()),
            )
            assert env.database.verify() is False

    def test_capture_and_verify_config(self) -> None:
        with DisposableEnvironment() as env:
            env.config.capture_baseline()
            assert env.config.verify() is True

            env.config.write_json("settings.json", {"app_name": "modified"})
            assert env.config.verify() is False

    def test_capture_and_verify_git(self) -> None:
        with DisposableEnvironment() as env:
            env.git_repo.capture_baseline()
            assert env.git_repo.verify() is True

            env.git_repo.add_file("new.txt", "new")
            env.git_repo.commit("new commit")
            assert env.git_repo.verify() is False

    def test_capture_and_verify_external_api(self) -> None:
        with DisposableEnvironment() as env:
            env.external_api.capture_baseline()
            assert env.external_api.verify() is True

            state = env.external_api.read_state()
            state["endpoints"]["/api/new"] = {"method": "DELETE", "status": "active"}
            env.external_api.write_state(state)
            assert env.external_api.verify() is False

    def test_capture_and_verify_infrastructure(self) -> None:
        with DisposableEnvironment() as env:
            env.infrastructure.capture_baseline()
            assert env.infrastructure.verify() is True

            env.infrastructure.create_resource("compute", "new-server")
            assert env.infrastructure.verify() is False


class TestFullEnvironmentVerification:
    """Verify the complete environment verification workflow."""

    def test_verify_restored_returns_detailed_report(self) -> None:
        with DisposableEnvironment() as env:
            baseline = env.compute_fingerprint()

            env.filesystem.capture_baseline()
            env.database.capture_baseline()
            env.git_repo.capture_baseline()
            env.config.capture_baseline()
            env.external_api.capture_baseline()
            env.infrastructure.capture_baseline()

            report = env.verify_restored(baseline)

            assert report["fully_restored"] is True
            assert report["fingerprint_match"] is True
            assert all(report["resources"].values())
            assert report["verification_method"] == "independent_external_state_verification"

    def test_verify_restored_detects_partial_damage(self) -> None:
        with DisposableEnvironment() as env:
            baseline = env.compute_fingerprint()

            env.filesystem.capture_baseline()
            env.database.capture_baseline()
            env.git_repo.capture_baseline()
            env.config.capture_baseline()
            env.external_api.capture_baseline()
            env.infrastructure.capture_baseline()

            env.filesystem.write("readme.txt", "MODIFIED CONTENT")

            report = env.verify_restored(baseline)

            assert report["fully_restored"] is False
            assert report["resources"]["filesystem"] is False
            assert report["resources"]["database"] is True


class TestFilesystemResourceOperations:
    """Verify filesystem resource supports all required operations."""

    def test_write_read_delete(self) -> None:
        with DisposableEnvironment() as env:
            env.filesystem.write("test.txt", "content")
            assert env.filesystem.read("test.txt") == "content"

            env.filesystem.delete("test.txt")
            files = _normalize_paths(env.filesystem.list_files())
            assert "test.txt" not in files

    def test_rename_file(self) -> None:
        with DisposableEnvironment() as env:
            env.filesystem.write("old.txt", "content")
            env.filesystem.rename("old.txt", "new.txt")

            files = _normalize_paths(env.filesystem.list_files())
            assert "new.txt" in files
            assert "old.txt" not in files

    def test_nested_directory_creation(self) -> None:
        with DisposableEnvironment() as env:
            env.filesystem.write("deep/nested/path/file.txt", "deep content")
            assert env.filesystem.read("deep/nested/path/file.txt") == "deep content"


class TestDatabaseResourceOperations:
    """Verify database resource supports all required operations."""

    def test_insert_update_delete(self) -> None:
        with DisposableEnvironment() as env:
            env.database.execute(
                "INSERT INTO users (username, email, role, created_at) VALUES (?, ?, ?, ?)",
                ("testuser", "test@example.com", "user", datetime.now(UTC).isoformat()),
            )
            user = env.database.fetch_one(
                "SELECT * FROM users WHERE username = ?", ("testuser",)
            )
            assert user is not None
            assert user["email"] == "test@example.com"

            env.database.execute(
                "UPDATE users SET email = ? WHERE username = ?",
                ("updated@example.com", "testuser"),
            )
            user = env.database.fetch_one(
                "SELECT * FROM users WHERE username = ?", ("testuser",)
            )
            assert user["email"] == "updated@example.com"

            env.database.execute(
                "DELETE FROM users WHERE username = ?", ("testuser",)
            )
            user = env.database.fetch_one(
                "SELECT * FROM users WHERE username = ?", ("testuser",)
            )
            assert user is None


class TestGitResourceOperations:
    """Verify git resource supports all required operations."""

    def test_commit_and_log(self) -> None:
        with DisposableEnvironment() as env:
            env.git_repo.add_file("feature.txt", "feature content")
            env.git_repo.commit("Add feature")

            log = env.git_repo.log()
            messages = [entry["message"] for entry in log]
            assert "Add feature" in messages

    def test_modify_and_commit(self) -> None:
        with DisposableEnvironment() as env:
            env.git_repo.modify_file("readme.txt", "Modified content")
            env.git_repo.add_file("readme.txt", "staged")
            env.git_repo.commit("Modify readme")

            log = env.git_repo.log()
            assert any("Modify readme" in entry["message"] for entry in log)


class TestInfrastructureResourceOperations:
    """Verify infrastructure resource supports all required operations."""

    def test_create_delete_resource(self) -> None:
        with DisposableEnvironment() as env:
            res = env.infrastructure.create_resource("compute", "test-server")
            assert res["type"] == "compute"
            assert res["name"] == "test-server"
            assert res["status"] == "provisioned"

            state = env.infrastructure.read_state()
            assert any(r["id"] == res["id"] for r in state["resources"])

            deleted = env.infrastructure.delete_resource(res["id"])
            assert deleted is True

            state = env.infrastructure.read_state()
            assert not any(r["id"] == res["id"] for r in state["resources"])

    def test_update_resource(self) -> None:
        with DisposableEnvironment() as env:
            res = env.infrastructure.create_resource("compute", "test-server")
            updated = env.infrastructure.update_resource(res["id"], status="stopped")

            assert updated is not None
            assert updated["status"] == "stopped"
            assert "updated_at" in updated
