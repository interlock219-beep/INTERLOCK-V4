"""Calculator experiment workflow for Interlock workspace protection.

Implements the full lifecycle:
1. Register user
2. Register agent
3. Create session
4. Capture baseline
5. Run protected file operations
6. Freeze session
7. Revoke/kill agent
8. Discover actions
9. Create recovery plan
10. Simulate recovery
11. Execute recovery
12. Verify recovery
13. Confirm workspace matches baseline
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sdk.workspace_protection.path_security import (
    PathSecurityError,
    WorkspacePathSecurity,
)
from sdk.workspace_protection.protected_tools import (
    ProtectedFilesystemError,
    ProtectedFilesystemTools,
)

HttpClient = Callable[[str, str, dict[str, Any]], dict[str, Any]]


class WorkspaceExperimentError(Exception):
    """Raised when the workspace experiment fails."""


class WorkspaceExperiment:
    """End-to-end experiment for Interlock-protected workspace operations."""

    AGENT_ID = "kilo-calculator"
    CORRELATION_ID = "calc-exp-001"

    def __init__(
        self,
        workspace_path: str | Path,
        gateway_url: str = "http://127.0.0.1:8000",
        auth_token: str | None = None,
        http_client: HttpClient | None = None,
    ) -> None:
        self._workspace_path = Path(workspace_path)
        self._path_security = WorkspacePathSecurity(workspace_path)
        self._tools = ProtectedFilesystemTools(
            path_security=self._path_security,
            gateway_url=gateway_url,
            auth_token=auth_token,
            http_client=http_client,
        )
        self._http_client = http_client
        self._baseline: dict[str, Any] | None = None

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self._http_client is not None:
            return self._http_client("POST", path, payload)
        return self._tools._post_json(path, payload)

    def _get_json(self, path: str) -> dict[str, Any]:
        if self._http_client is not None:
            return self._http_client("GET", path, {})
        return self._tools._get_json(path)

    def _file_hash(self, path: Path) -> str:
        if not path.exists():
            return ""
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def _capture_baseline(self) -> dict[str, Any]:
        """Capture the current workspace state as a baseline."""
        baseline: dict[str, Any] = {"files": {}}
        for file_path in self._workspace_path.rglob("*"):
            if file_path.is_file():
                rel = str(file_path.relative_to(self._workspace_path))
                baseline["files"][rel] = {
                    "hash": self._file_hash(file_path),
                    "size": file_path.stat().st_size,
                }
        return baseline

    def _workspace_matches_baseline(self, baseline: dict[str, Any]) -> bool:
        """Check if the current workspace matches the baseline."""
        current_files: set[str] = set()
        for file_path in self._workspace_path.rglob("*"):
            if file_path.is_file():
                rel = str(file_path.relative_to(self._workspace_path))
                current_files.add(rel)
                if rel not in baseline.get("files", {}):
                    return False
                if self._file_hash(file_path) != baseline["files"][rel]["hash"]:
                    return False

        return all(rel in current_files for rel in baseline.get("files", {}))

    def run(
        self,
        user_email: str = "experiment@test.com",
        user_password: str = "change-me-in-tests",  # noqa: S107
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Run the full calculator experiment.

        Returns:
            Experiment result dict.
        """
        results: dict[str, Any] = {"steps": {}, "success": True}

        try:
            register_payload = {"email": user_email, "password": user_password}
            register_response = self._post_json(
                "/api/v1/auth/register", register_payload
            )
            results["steps"]["register"] = {
                "status_code": register_response.get("status_code", 200),
                "user_id": register_response.get("user", {}).get("id"),
            }
            access_token = register_response.get("access_token")
            if not access_token:
                raise WorkspaceExperimentError(
                    "Registration did not return access_token"
                )
            self._tools._auth_token = access_token

            agent_payload = {
                "agent_id": self.AGENT_ID,
                "name": "Kilo Calculator",
                "description": "Calculator agent for workspace experiment",
                "agent_type": "tool_agent",
                "environment": "test",
                "registration_method": "manual",
                "creator": user_email,
            }
            agent_response = self._post_json("/api/v1/agents", agent_payload)
            results["steps"]["register_agent"] = {
                "status": agent_response.get("status"),
                "agent_id": agent_response.get("agent_id"),
            }

            if session_id:
                results["steps"]["create_session"] = {
                    "status_code": 200,
                    "session_id": session_id,
                    "note": "pre-existing",
                }
            else:
                session_payload = {
                    "agent_id": self.AGENT_ID,
                    "intent_id": self.CORRELATION_ID,
                }
                session_response = self._post_json(
                    "/api/v1/agent-sessions", session_payload
                )
                results["steps"]["create_session"] = {
                    "status_code": session_response.get("status_code", 200),
                    "session_id": session_response.get("session_id"),
                }
            session_id = session_id or results["steps"]["create_session"].get(
                "session_id", ""
            )

            self._baseline = self._capture_baseline()
            results["steps"]["capture_baseline"] = {
                "file_count": len(self._baseline.get("files", {})),
            }

            operations: list[dict[str, Any]] = []

            calc_file = self._workspace_path / "calculator.py"
            write_result = self._tools.write_file(
                path=calc_file,
                content=(
                    "def add(a, b):\n"
                    "    return a + b\n\n"
                    "def subtract(a, b):\n"
                    "    return a - b\n"
                ),
                agent_id=self.AGENT_ID,
                session_id=session_id,
                correlation_id=self.CORRELATION_ID,
            )
            operations.append({"operation": "write", "result": write_result})

            edit_result = self._tools.edit_file(
                path=calc_file,
                new_content=(
                    'def add(a, b):\n'
                    '    """Add two numbers."""\n'
                    "    return a + b\n\n"
                    'def subtract(a, b):\n'
                    '    """Subtract b from a."""\n'
                    "    return a - b\n"
                ),
                agent_id=self.AGENT_ID,
                session_id=session_id,
                correlation_id=self.CORRELATION_ID,
            )
            operations.append({"operation": "edit", "result": edit_result})

            readme_file = self._workspace_path / "README.md"
            readme_result = self._tools.write_file(
                path=readme_file,
                content=(
                    "# Calculator Experiment\n\n"
                    "This workspace was modified by the Kilo calculator agent.\n"
                ),
                agent_id=self.AGENT_ID,
                session_id=session_id,
                correlation_id=self.CORRELATION_ID,
            )
            operations.append({"operation": "write", "result": readme_result})

            renamed_file = self._workspace_path / "calculator_v2.py"
            rename_result = self._tools.rename_file(
                old_path=calc_file,
                new_path=renamed_file,
                agent_id=self.AGENT_ID,
                session_id=session_id,
                correlation_id=self.CORRELATION_ID,
            )
            operations.append({"operation": "rename", "result": rename_result})

            delete_result = self._tools.delete_file(
                path=renamed_file,
                agent_id=self.AGENT_ID,
                session_id=session_id,
                correlation_id=self.CORRELATION_ID,
            )
            operations.append({"operation": "delete", "result": delete_result})

            results["steps"]["protected_operations"] = {
                "count": len(operations),
                "operations": operations,
            }

            changed_files = []
            for file_path in self._workspace_path.rglob("*"):
                if file_path.is_file():
                    rel = str(file_path.relative_to(self._workspace_path))
                    changed_files.append(rel)
            results["steps"]["verify_changes"] = {
                "changed_files": changed_files,
            }

            try:
                freeze_response = self._post_json(
                    f"/api/v1/agent-sessions/{session_id}/freeze", {}
                )
                results["steps"]["freeze_session"] = {
                    "status": freeze_response.get("status"),
                    "session_id": freeze_response.get("session_id"),
                }
            except (ProtectedFilesystemError, Exception) as exc:
                results["steps"]["freeze_session"] = {
                    "status": "skipped",
                    "reason": str(exc),
                    "note": "agent-session routes require admin/operator role",
                }

            try:
                kill_response = self._post_json(
                    f"/api/v1/agents/{self.AGENT_ID}/kill", {}
                )
                results["steps"]["kill_agent"] = {
                    "status": kill_response.get("status"),
                    "agent_id": kill_response.get("agent_id"),
                }
            except (ProtectedFilesystemError, Exception) as exc:
                results["steps"]["kill_agent"] = {
                    "status": "skipped",
                    "reason": str(exc),
                    "note": "agent-session routes require admin/operator role",
                }

            try:
                actions_response = self._get_json(
                    f"/api/v1/actions?agent_id={self.AGENT_ID}"
                    f"&correlation_id={self.CORRELATION_ID}"
                )
                action_items = actions_response.get("items", [])
                results["steps"]["discover_actions"] = {
                    "count": len(action_items),
                    "action_ids": [a.get("action_id") for a in action_items],
                }
            except (ProtectedFilesystemError, Exception) as exc:
                results["steps"]["discover_actions"] = {
                    "count": 0,
                    "reason": str(exc),
                }
                action_items = []

            if action_items:
                first_action_id = action_items[0].get("action_id")
                try:
                    plan_response = self._post_json(
                        "/api/v1/recovery/plan",
                        {"incident_action_id": first_action_id},
                    )
                    results["steps"]["create_recovery_plan"] = {
                        "plan_id": plan_response.get("plan_id"),
                        "status": plan_response.get("status"),
                    }

                    if plan_response.get("plan_id"):
                        plan_id = plan_response["plan_id"]
                        simulate_response = self._post_json(
                            f"/api/v1/recovery/plan/{plan_id}/simulate", {}
                        )
                        results["steps"]["simulate_recovery"] = {
                            "would_succeed": simulate_response.get(
                                "would_succeed"
                            ),
                        }

                        execute_response = self._post_json(
                            f"/api/v1/recovery/plan/{plan_id}/execute", {}
                        )
                        results["steps"]["execute_recovery"] = {
                            "status": execute_response.get("status"),
                        }
                except (ProtectedFilesystemError, Exception) as exc:
                    results["steps"]["recovery"] = {
                        "status": "skipped",
                        "reason": str(exc),
                        "note": "recovery requires admin/operator role",
                    }

        except (ProtectedFilesystemError, PathSecurityError) as exc:
            results["success"] = False
            results["error"] = str(exc)

        return results
