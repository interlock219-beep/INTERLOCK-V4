"""Protected filesystem tools for Interlock workspace integration.

Every mutation is authorized through Interlock before touching the filesystem.
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from sdk.workspace_protection.path_security import (
    WorkspacePathSecurity,
)


class ProtectedFilesystemError(Exception):
    """Raised when a protected filesystem operation fails."""


class ProtectedFilesystemTools:
    """Interlock-protected filesystem operations.

    The execution path is:
        Kilo -> protected tool -> Interlock (authorization) -> filesystem

    Direct filesystem access is OUTSIDE the protection boundary.
    """

    def __init__(
        self,
        path_security: WorkspacePathSecurity,
        gateway_url: str = "http://127.0.0.1:8000",
        auth_token: str | None = None,
        tenant_id: str | None = None,
        http_client: Any = None,
    ) -> None:
        self._path_security = path_security
        self._gateway_url = gateway_url.rstrip("/")
        self._auth_token = auth_token
        self._tenant_id = tenant_id
        self._http_client = http_client

    def _auth_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"
        return headers

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self._http_client is not None:
            return cast(dict[str, Any], self._http_client("POST", path, payload))
        url = f"{self._gateway_url}{path}"
        body = json.dumps(payload).encode("utf-8")
        request = Request(  # noqa: S310
            url,
            data=body,
            headers={**self._auth_headers(), "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=10) as response:  # noqa: S310
                return cast(dict[str, Any], json.loads(response.read().decode("utf-8")))
        except HTTPError as exc:
            raise ProtectedFilesystemError(
                f"Interlock request failed: {exc.code} {exc.reason}"
            ) from exc
        except URLError as exc:
            raise ProtectedFilesystemError(
                f"Interlock request failed: {exc.reason}"
            ) from exc

    def _get_json(self, path: str) -> dict[str, Any]:
        if self._http_client is not None:
            return self._http_client("GET", path, {})  # type: ignore
        url = f"{self._gateway_url}{path}"
        request = Request(url, headers=self._auth_headers(), method="GET")  # noqa: S310
        try:
            with urlopen(request, timeout=10) as response:  # noqa: S310
                return cast(dict[str, Any], json.loads(response.read().decode("utf-8")))
        except HTTPError as exc:
            raise ProtectedFilesystemError(
                f"Interlock request failed: {exc.code} {exc.reason}"
            ) from exc
        except URLError as exc:
            raise ProtectedFilesystemError(
                f"Interlock request failed: {exc.reason}"
            ) from exc


    def _update_execution_result(
        self, action_id: str, after_snapshot: dict[str, Any] | None
    ) -> dict[str, Any]:
        """Report execution result back to Interlock after a filesystem mutation."""
        payload = {
            "status": "executed",
            "after_state_ref": (
                f"fs:{after_snapshot['hash']}"
                if after_snapshot and after_snapshot.get("hash")
                else None
            ),
            "after_state_snapshot": after_snapshot,
        }
        return self._patch_json(f"/api/v1/actions/{action_id}/execution", payload)

    def _patch_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self._http_client is not None:
            return cast(dict[str, Any], self._http_client("PATCH", path, payload))
        url = f"{self._gateway_url}{path}"
        body = json.dumps(payload).encode("utf-8")
        request = Request(  # noqa: S310
            url,
            data=body,
            headers={**self._auth_headers(), "Content-Type": "application/json"},
            method="PATCH",
        )
        try:
            with urlopen(request, timeout=10) as response:  # noqa: S310
                return cast(dict[str, Any], json.loads(response.read().decode("utf-8")))
        except HTTPError as exc:
            raise ProtectedFilesystemError(
                f"Interlock request failed: {exc.code} {exc.reason}"
            ) from exc
        except URLError as exc:
            raise ProtectedFilesystemError(
                f"Interlock request failed: {exc.reason}"
            ) from exc

    def _capture_snapshot(self, file_path: Path) -> dict[str, Any] | None:
        """Capture a BYTE-EXACT file snapshot for recovery evidence.

        CRITICAL: This method reads the raw bytes from disk and hashes those
        exact bytes.  It NEVER normalizes line endings, encoding, whitespace,
        or final newlines.  Using ``read_text`` previously caused LF-only files
        to be captured as CRLF (or vice-versa), producing a wrong before-state
        that the recovery system then restored.

        Returns ``None`` only when the file cannot be reliably captured; the
        caller must treat a missing snapshot as NOT safely recoverable.
        """
        try:
            if not file_path.exists():
                return {
                    "exists": False,
                    "content": None,
                    "content_b64": None,
                    "hash": None,
                    "size": 0,
                    "metadata": None,
                    "binary": False,
                    "byte_exact": True,
                }

            stat_result = file_path.stat()
            metadata = {
                "mode": stat_result.st_mode,
                "uid": stat_result.st_uid,
                "gid": stat_result.st_gid,
                "mtime": stat_result.st_mtime,
                "atime": stat_result.st_atime,
            }

            # Read the EXACT bytes from disk.  No decoding, no normalization.
            raw_bytes = file_path.read_bytes()
            content_hash = hashlib.sha256(raw_bytes).hexdigest()

            # Try to represent content as a UTF-8 string for text files, but
            # ALWAYS keep the raw bytes available via content_b64 so that the
            # recovery adapter can restore the EXACT original bytes regardless
            # of encoding, BOM, or line-ending differences.
            content_b64 = base64.b64encode(raw_bytes).decode("ascii")
            is_binary = False
            text_content: str | None = None
            try:
                text_content = raw_bytes.decode("utf-8")
                # If the decoded text re-encodes to the same bytes, we have a
                # clean UTF-8 text file.  Otherwise treat as binary.
                if text_content.encode("utf-8") != raw_bytes:
                    is_binary = True
                    text_content = None
            except UnicodeDecodeError:
                is_binary = True
                text_content = None

            return {
                "exists": True,
                "content": text_content,
                "content_b64": content_b64,
                "raw_bytes_length": len(raw_bytes),
                "hash": content_hash,
                "size": stat_result.st_size,
                "metadata": metadata,
                "binary": is_binary,
                "byte_exact": True,
            }
        except Exception as exc:
            raise ProtectedFilesystemError(
                f"Failed to capture byte-exact snapshot of {file_path}: {exc}"
            ) from exc

    def _register_action(
        self,
        agent_id: str,
        session_id: str,
        correlation_id: str,
        tool: str,
        resource: str,
        action_type: str,
        before_snapshot: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Register a ProtectedAction with Interlock."""
        payload = {
            "agent_id": agent_id,
            "tool": tool,
            "resource": resource,
            "action_type": action_type,
            "correlation_id": correlation_id,
            "before_state_ref": (
                f"fs:{before_snapshot['hash']}"
                if before_snapshot and before_snapshot.get("hash")
                else None
            ),
            "before_state_snapshot": before_snapshot,
            "tool_arguments": {
                "session_id": session_id,
                "correlation_id": correlation_id,
            },
        }
        return self._post_json("/api/v1/actions/", payload)

    def _evaluate_action(self, action_id: str) -> dict[str, Any]:
        """Evaluate a ProtectedAction with Interlock."""
        return self._post_json(f"/api/v1/actions/{action_id}/evaluate", {})

    def _get_execution_token(
        self, agent_id: str, tool_name: str, tool_arguments: dict[str, Any]
    ) -> str:
        """Verify intent with Interlock and return an ephemeral execution token."""
        verify_payload = {
            "user_prompt": f"Protected filesystem operation: {tool_name}",
            "agent_id": agent_id,
            "reasoning_step": f"Execute {tool_name}",
            "proposed_tool": tool_name,
            "tool_arguments": tool_arguments,
            "tenant_id": self._tenant_id,
        }
        verify_response = self._post_json("/api/v1/intent/verify", verify_payload)
        ephemeral_token = str(verify_response.get("ephemeral_token") or "")
        if not ephemeral_token:
            raise ProtectedFilesystemError("Interlock did not return an execution token.")
        return ephemeral_token

    def _log_execution_intent(self, ephemeral_token: str) -> None:
        """Log execution intent with Interlock without consuming the token.

        This performs an authoritative containment check (peek) so that
        a frozen/quarantined/revoked agent is rejected before we reach
        the local mutation gate.
        """
        payload = {"execution_token": ephemeral_token}
        self._post_json("/api/v1/intent/execute", payload)

    def _authorize_mutation(
        self,
        agent_id: str,
        session_id: str,
    ) -> None:
        """Authoritative pre-mutation gate.

        Performs a final containment check immediately before the local
        filesystem mutation.  The execution token has already been
        consumed by ``_log_execution_intent``; this gate relies on the
        caller's authenticated identity and the supplied agent/session
        identifiers.
        """
        payload = {
            "agent_id": agent_id,
            "session_id": session_id,
        }
        result = self._post_json("/api/v1/intent/authorize-mutation", payload)
        if result.get("status") != "mutation_authorized":
            raise ProtectedFilesystemError(
                "Interlock denied mutation authorization: "
                f"{result.get('status', 'unknown')}"
            )

    def _perform_write(
        self, resolved_path: Path, content: str | bytes, binary: bool = False
    ) -> None:
        """Perform the actual filesystem write operation.

        CRITICAL: Always writes the EXACT bytes provided.  Using
        ``write_text`` on some platforms can normalize line endings
        (e.g. ``\\n`` -> ``\\r\\n`` on Windows), which would corrupt the
        before-state snapshot and make exact recovery impossible.
        """
        resolved_path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, str):
            # Encode using UTF-8 and write the exact bytes.  This preserves
            # any CRLF / CR / LF sequences the caller intended.
            resolved_path.write_bytes(content.encode("utf-8"))
        elif isinstance(content, bytes):
            resolved_path.write_bytes(content)
        else:
            raise ProtectedFilesystemError(
                f"Unsupported content type for write: {type(content).__name__}"
            )

    def _perform_delete(self, resolved_path: Path) -> None:
        """Perform the actual filesystem delete operation."""
        if resolved_path.exists():
            resolved_path.unlink()

    def _perform_rename(self, resolved_path: Path, new_resolved_path: Path) -> None:
        """Perform the actual filesystem rename operation."""
        resolved_path.rename(new_resolved_path)

    def write_file(
        self,
        path: str | Path,
        content: str | bytes,
        agent_id: str,
        session_id: str,
        correlation_id: str,
        binary: bool = False,
    ) -> dict[str, Any]:
        """Write content to a file after Interlock authorization.

        Args:
            path: Target file path (must be within workspace).
            content: Content to write.
            agent_id: Agent identifier.
            session_id: Session identifier.
            correlation_id: Correlation identifier.
            binary: If True, content is treated as bytes.

        Returns:
            Result dict with action_id and path.

        Raises:
            PathSecurityError: If path is outside workspace.
            ProtectedFilesystemError: If Interlock denies the operation.
        """
        resolved_path = self._path_security.validate(path)
        before_snapshot = self._capture_snapshot(resolved_path)

        action = self._register_action(
            agent_id=agent_id,
            session_id=session_id,
            correlation_id=correlation_id,
            tool="filesystem",
            resource=str(resolved_path.relative_to(self._path_security.workspace_path)),
            action_type="write",
            before_snapshot=before_snapshot,
        )

        try:
            evaluation = self._evaluate_action(action["action_id"])
            if evaluation.get("status") not in ("permitted", "executed"):
                raise ProtectedFilesystemError(
                    f"Interlock denied write: {evaluation.get('decision_reason', 'unknown')}"
                )

            tool_arguments = {
                "session_id": session_id,
                "correlation_id": correlation_id,
                "path": str(resolved_path.relative_to(self._path_security.workspace_path)),
                "action_type": "write",
            }
            ephemeral_token = self._get_execution_token(agent_id, "write_file", tool_arguments)
            self._log_execution_intent(ephemeral_token)
            self._authorize_mutation(agent_id, session_id)

            self._perform_write(resolved_path, content, binary=binary)

            after_snapshot = self._capture_snapshot(resolved_path)
            self._update_execution_result(action["action_id"], after_snapshot)

            return {
                "action_id": action["action_id"],
                "path": str(resolved_path),
                "status": "written",
                "agent_id": agent_id,
                "session_id": session_id,
                "correlation_id": correlation_id,
            }
        except Exception:
            raise

    def edit_file(
        self,
        path: str | Path,
        new_content: str,
        agent_id: str,
        session_id: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        """Edit an existing file after Interlock authorization.

        Args:
            path: Target file path (must be within workspace).
            new_content: New content for the file.
            agent_id: Agent identifier.
            session_id: Session identifier.
            correlation_id: Correlation identifier.

        Returns:
            Result dict with action_id and path.

        Raises:
            PathSecurityError: If path is outside workspace.
            ProtectedFilesystemError: If Interlock denies the operation.
        """
        resolved_path = self._path_security.validate(path)
        if not resolved_path.exists():
            raise ProtectedFilesystemError(f"File does not exist: {resolved_path}")

        before_snapshot = self._capture_snapshot(resolved_path)

        action = self._register_action(
            agent_id=agent_id,
            session_id=session_id,
            correlation_id=correlation_id,
            tool="filesystem",
            resource=str(resolved_path.relative_to(self._path_security.workspace_path)),
            action_type="modify",
            before_snapshot=before_snapshot,
        )

        try:
            evaluation = self._evaluate_action(action["action_id"])
            if evaluation.get("status") not in ("permitted", "executed"):
                raise ProtectedFilesystemError(
                    f"Interlock denied edit: {evaluation.get('decision_reason', 'unknown')}"
                )

            tool_arguments = {
                "session_id": session_id,
                "correlation_id": correlation_id,
                "path": str(resolved_path.relative_to(self._path_security.workspace_path)),
                "action_type": "modify",
            }
            ephemeral_token = self._get_execution_token(agent_id, "edit_file", tool_arguments)
            self._log_execution_intent(ephemeral_token)
            self._authorize_mutation(agent_id, session_id)

            self._perform_write(resolved_path, new_content, binary=False)

            after_snapshot = self._capture_snapshot(resolved_path)
            self._update_execution_result(action["action_id"], after_snapshot)

            return {
                "action_id": action["action_id"],
                "path": str(resolved_path),
                "status": "edited",
                "agent_id": agent_id,
                "session_id": session_id,
                "correlation_id": correlation_id,
            }
        except Exception:
            raise

    def delete_file(
        self,
        path: str | Path,
        agent_id: str,
        session_id: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        """Delete a file after Interlock authorization.

        Args:
            path: Target file path (must be within workspace).
            agent_id: Agent identifier.
            session_id: Session identifier.
            correlation_id: Correlation identifier.

        Returns:
            Result dict with action_id and path.

        Raises:
            PathSecurityError: If path is outside workspace.
            ProtectedFilesystemError: If Interlock denies the operation.
        """
        resolved_path = self._path_security.validate(path)
        before_snapshot = self._capture_snapshot(resolved_path)

        action = self._register_action(
            agent_id=agent_id,
            session_id=session_id,
            correlation_id=correlation_id,
            tool="filesystem",
            resource=str(resolved_path.relative_to(self._path_security.workspace_path)),
            action_type="delete",
            before_snapshot=before_snapshot,
        )

        try:
            evaluation = self._evaluate_action(action["action_id"])
            if evaluation.get("status") not in ("permitted", "executed"):
                raise ProtectedFilesystemError(
                    f"Interlock denied delete: {evaluation.get('decision_reason', 'unknown')}"
                )

            tool_arguments = {
                "session_id": session_id,
                "correlation_id": correlation_id,
                "path": str(resolved_path.relative_to(self._path_security.workspace_path)),
                "action_type": "delete",
            }
            ephemeral_token = self._get_execution_token(agent_id, "delete_file", tool_arguments)
            self._log_execution_intent(ephemeral_token)
            self._authorize_mutation(agent_id, session_id)

            self._perform_delete(resolved_path)

            after_snapshot = self._capture_snapshot(resolved_path)
            self._update_execution_result(action["action_id"], after_snapshot)

            return {
                "action_id": action["action_id"],
                "path": str(resolved_path),
                "status": "deleted",
                "agent_id": agent_id,
                "session_id": session_id,
                "correlation_id": correlation_id,
            }
        except Exception:
            raise

    def rename_file(
        self,
        old_path: str | Path,
        new_path: str | Path,
        agent_id: str,
        session_id: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        """Rename a file after Interlock authorization.

        Args:
            old_path: Current file path (must be within workspace).
            new_path: Target file path (must be within workspace).
            agent_id: Agent identifier.
            session_id: Session identifier.
            correlation_id: Correlation identifier.

        Returns:
            Result dict with action_id, old_path, and new_path.

        Raises:
            PathSecurityError: If either path is outside workspace.
            ProtectedFilesystemError: If Interlock denies the operation.
        """
        resolved_old = self._path_security.validate(old_path)
        resolved_new = self._path_security.validate(new_path)

        if not resolved_old.exists():
            raise ProtectedFilesystemError(f"Source file does not exist: {resolved_old}")

        before_snapshot = self._capture_snapshot(resolved_old)

        action = self._register_action(
            agent_id=agent_id,
            session_id=session_id,
            correlation_id=correlation_id,
            tool="filesystem",
            resource=str(resolved_old.relative_to(self._path_security.workspace_path)),
            action_type="rename",
            before_snapshot=before_snapshot,
        )

        try:
            evaluation = self._evaluate_action(action["action_id"])
            if evaluation.get("status") not in ("permitted", "executed"):
                raise ProtectedFilesystemError(
                    f"Interlock denied rename: {evaluation.get('decision_reason', 'unknown')}"
                )

            tool_arguments = {
                "session_id": session_id,
                "correlation_id": correlation_id,
                "old_path": str(resolved_old.relative_to(self._path_security.workspace_path)),
                "new_path": str(resolved_new.relative_to(self._path_security.workspace_path)),
                "action_type": "rename",
            }
            ephemeral_token = self._get_execution_token(agent_id, "rename_file", tool_arguments)
            self._log_execution_intent(ephemeral_token)
            self._authorize_mutation(agent_id, session_id)

            self._perform_rename(resolved_old, resolved_new)

            after_snapshot = self._capture_snapshot(resolved_new)
            self._update_execution_result(action["action_id"], after_snapshot)

            return {
                "action_id": action["action_id"],
                "old_path": str(resolved_old),
                "new_path": str(resolved_new),
                "status": "renamed",
                "agent_id": agent_id,
                "session_id": session_id,
                "correlation_id": correlation_id,
            }
        except Exception:
            raise
