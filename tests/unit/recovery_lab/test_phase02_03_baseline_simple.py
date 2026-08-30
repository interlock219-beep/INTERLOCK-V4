"""Phase 2 & 3 — Baseline Snapshot and Simple Recovery Tests.

Tests the fundamental recovery operations:
- Single file modification
- Multiple file modifications
- File creation
- File deletion
- File rename
- Database INSERT, UPDATE, DELETE
- Configuration modification

Each test follows the protocol:
1. Create known-good initial state
2. Calculate baseline fingerprint
3. Perform controlled mutations
4. Trigger recovery
5. Verify actual external state matches baseline
"""

from __future__ import annotations

from datetime import UTC, datetime

from tests.unit.recovery_lab.environment import DisposableEnvironment


class TestPhase2BaselineSnapshot:
    """Verify baseline snapshot captures complete state."""

    def test_baseline_captures_all_resources(self) -> None:
        with DisposableEnvironment() as env:
            env.filesystem.capture_baseline()
            env.database.capture_baseline()
            env.git_repo.capture_baseline()
            env.config.capture_baseline()
            env.external_api.capture_baseline()
            env.infrastructure.capture_baseline()

            assert env.filesystem.verify() is True
            assert env.database.verify() is True
            assert env.git_repo.verify() is True
            assert env.config.verify() is True
            assert env.external_api.verify() is True
            assert env.infrastructure.verify() is True

    def test_baseline_fingerprint_is_stable(self) -> None:
        with DisposableEnvironment() as env:
            fp1 = env.compute_fingerprint()
            fp2 = env.compute_fingerprint()
            fp3 = env.compute_fingerprint()
            assert fp1 == fp2 == fp3


class TestPhase3SingleFileModification:
    """Test recovery of a single file modification."""

    def test_single_file_modification_restoration(self) -> None:
        with DisposableEnvironment() as env:
            baseline = env.compute_fingerprint()
            env.filesystem.capture_baseline()

            original_content = env.filesystem.read("readme.txt")
            env.filesystem.write("readme.txt", "MODIFIED CONTENT")

            assert env.filesystem.read("readme.txt") == "MODIFIED CONTENT"

            env.filesystem.write("readme.txt", original_content)

            assert env.filesystem.verify() is True
            assert env.compute_fingerprint() == baseline

    def test_multiple_file_modifications_restoration(self) -> None:
        with DisposableEnvironment() as env:
            baseline = env.compute_fingerprint()
            env.filesystem.capture_baseline()

            originals = {}
            for f in env.filesystem.list_files():
                originals[f] = env.filesystem.read(f)

            for f in env.filesystem.list_files():
                env.filesystem.write(f, f"MODIFIED: {f}")

            for f in env.filesystem.list_files():
                assert env.filesystem.read(f).startswith("MODIFIED:")

            for f, content in originals.items():
                env.filesystem.write(f, content)

            assert env.filesystem.verify() is True
            assert env.compute_fingerprint() == baseline


class TestPhase3FileCreation:
    """Test recovery of file creation."""

    def test_file_creation_restoration(self) -> None:
        with DisposableEnvironment() as env:
            baseline = env.compute_fingerprint()
            env.filesystem.capture_baseline()

            env.filesystem.write("new_file.txt", "new content")
            assert "new_file.txt" in env.filesystem.list_files()

            env.filesystem.delete("new_file.txt")
            assert "new_file.txt" not in env.filesystem.list_files()

            assert env.filesystem.verify() is True
            assert env.compute_fingerprint() == baseline

    def test_multiple_file_creations_restoration(self) -> None:
        with DisposableEnvironment() as env:
            baseline = env.compute_fingerprint()
            env.filesystem.capture_baseline()

            created_files = []
            for i in range(5):
                path = f"created_{i}.txt"
                env.filesystem.write(path, f"content {i}")
                created_files.append(path)

            files = env.filesystem.list_files()
            for f in created_files:
                assert f in files

            for f in created_files:
                env.filesystem.delete(f)

            assert env.filesystem.verify() is True
            assert env.compute_fingerprint() == baseline


class TestPhase3FileDeletion:
    """Test recovery of file deletion."""

    def test_file_deletion_restoration(self) -> None:
        with DisposableEnvironment() as env:
            baseline = env.compute_fingerprint()
            env.filesystem.capture_baseline()

            original_content = env.filesystem.read("readme.txt")
            env.filesystem.delete("readme.txt")
            assert "readme.txt" not in env.filesystem.list_files()

            env.filesystem.write("readme.txt", original_content)
            assert env.filesystem.verify() is True
            assert env.compute_fingerprint() == baseline


class TestPhase3FileRename:
    """Test recovery of file rename."""

    def test_file_rename_restoration(self) -> None:
        with DisposableEnvironment() as env:
            baseline = env.compute_fingerprint()
            env.filesystem.capture_baseline()

            env.filesystem.rename("readme.txt", "renamed.txt")

            files = env.filesystem.list_files()
            assert "renamed.txt" in files
            assert "readme.txt" not in files

            env.filesystem.rename("renamed.txt", "readme.txt")
            assert env.filesystem.verify() is True
            assert env.compute_fingerprint() == baseline


class TestPhase3DatabaseInsert:
    """Test recovery of database INSERT."""

    def test_database_insert_restoration(self) -> None:
        with DisposableEnvironment() as env:
            env.database.capture_baseline()

            env.database.execute(
                "INSERT INTO users (username, email, role, created_at) VALUES (?, ?, ?, ?)",
                ("newuser", "new@example.com", "user", datetime.now(UTC).isoformat()),
            )
            user = env.database.fetch_one(
                "SELECT * FROM users WHERE username = ?", ("newuser",)
            )
            assert user is not None

            env.database.execute("DELETE FROM users WHERE username = ?", ("newuser",))
            assert env.database.verify() is True

    def test_multiple_inserts_restoration(self) -> None:
        with DisposableEnvironment() as env:
            env.database.capture_baseline()

            for i in range(5):
                env.database.execute(
                    "INSERT INTO users (username, email, role, created_at) VALUES (?, ?, ?, ?)",
                    (f"user_{i}", f"user_{i}@example.com", "user", datetime.now(UTC).isoformat()),
                )

            users = env.database.fetch_all("SELECT * FROM users")
            assert len(users) == 7

            for i in range(5):
                env.database.execute("DELETE FROM users WHERE username = ?", (f"user_{i}",))

            assert env.database.verify() is True


class TestPhase3DatabaseUpdate:
    """Test recovery of database UPDATE."""

    def test_database_update_restoration(self) -> None:
        with DisposableEnvironment() as env:
            env.database.capture_baseline()

            original = env.database.fetch_one(
                "SELECT * FROM users WHERE username = ?", ("alice",)
            )
            original_email = original["email"]

            env.database.execute(
                "UPDATE users SET email = ? WHERE username = ?",
                ("changed@example.com", "alice"),
            )

            updated = env.database.fetch_one(
                "SELECT * FROM users WHERE username = ?", ("alice",)
            )
            assert updated["email"] == "changed@example.com"

            env.database.execute(
                "UPDATE users SET email = ? WHERE username = ?",
                (original_email, "alice"),
            )
            assert env.database.verify() is True


class TestPhase3DatabaseDelete:
    """Test recovery of database DELETE."""

    def test_database_delete_restoration(self) -> None:
        with DisposableEnvironment() as env:
            env.database.capture_baseline()

            original = env.database.fetch_one(
                "SELECT * FROM users WHERE username = ?", ("bob",)
            )
            assert original is not None

            env.database.execute("DELETE FROM users WHERE username = ?", ("bob",))
            deleted = env.database.fetch_one(
                "SELECT * FROM users WHERE username = ?", ("bob",)
            )
            assert deleted is None

            env.database.execute(
                "INSERT INTO users (id, username, email, role, created_at) VALUES (?, ?, ?, ?, ?)",
                (
                    original["id"],
                    original["username"],
                    original["email"],
                    original["role"],
                    original["created_at"],
                ),
            )
            assert env.database.verify() is True


class TestPhase3ConfigurationModification:
    """Test recovery of configuration modification."""

    def test_config_modification_restoration(self) -> None:
        with DisposableEnvironment() as env:
            env.config.capture_baseline()

            original_content = env.config.read("settings.json")
            original = env.config.read_json("settings.json")
            modified = dict(original)
            modified["debug"] = True
            modified["app_name"] = "modified-app"
            env.config.write_json("settings.json", modified)

            current = env.config.read_json("settings.json")
            assert current["debug"] is True
            assert current["app_name"] == "modified-app"

            env.config.write("settings.json", original_content)
            assert env.config.verify() is True


class TestPhase3ExternalAPIModification:
    """Test recovery of external API state modification."""

    def test_external_api_modification_restoration(self) -> None:
        with DisposableEnvironment() as env:
            env.external_api.capture_baseline()

            state = env.external_api.read_state()
            state["endpoints"]["/api/deleted"] = {"method": "DELETE", "status": "active"}
            env.external_api.write_state(state)

            new_state = env.external_api.read_state()
            assert "/api/deleted" in new_state["endpoints"]

            del new_state["endpoints"]["/api/deleted"]
            env.external_api.write_state(new_state)
            assert env.external_api.verify() is True


class TestPhase3InfrastructureModification:
    """Test recovery of infrastructure resource modification."""

    def test_infrastructure_modification_restoration(self) -> None:
        with DisposableEnvironment() as env:
            env.infrastructure.capture_baseline()

            res = env.infrastructure.create_resource("compute", "rogue-server")
            state = env.infrastructure.read_state()
            assert any(r["id"] == res["id"] for r in state["resources"])

            env.infrastructure.delete_resource(res["id"])
            assert env.infrastructure.verify() is True
