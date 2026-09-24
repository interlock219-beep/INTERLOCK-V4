from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.domain.entities.snapshot_types import (
    RetentionPolicy,
    SnapshotChunk,
    SnapshotRecord,
    SnapshotType,
    apply_delta,
)
from app.domain.repositories.snapshot_repository import (
    InMemorySnapshotRepository,
    SnapshotRepository,
)


@dataclass(frozen=True, slots=True)
class SnapshotReadiness:
    """Recovery readiness assessment for a tenant."""

    tenant_id: str
    ready: bool
    latest_snapshot_id: str | None
    latest_snapshot_age_seconds: float
    total_snapshots: int
    total_size_bytes: int
    expired_snapshots: int
    unverified_snapshots: int
    lineage_depth_max: int
    storage_healthy: bool
    issues: list[str]
    recommendations: list[str]


def _validate_tenant_id(tenant_id: str) -> str:
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise ValueError("tenant_id must be a non-empty string")
    return tenant_id


def _as_bytes(value: bytes | bytearray | memoryview | str) -> bytes:
    if isinstance(value, str):
        return value.encode()
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value)
    raise TypeError("snapshot data must be bytes-like or str")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _decode_delta(chunks: tuple[SnapshotChunk, ...], key: bytes | None) -> bytes:
    sequences = [chunk.sequence for chunk in chunks]
    if sequences != list(range(len(chunks))):
        raise ValueError("Incremental chunk sequences are invalid")
    return b"".join(chunk.decrypt_and_decompress(key) for chunk in chunks)


class SnapshotIntelligenceService:
    """Service for snapshot capture, incremental reconstruction, verification, and retention."""

    def __init__(
        self,
        repository: SnapshotRepository | None = None,
        default_encryption_key: bytes | None = None,
        chunk_size: int = 64 * 1024,
    ) -> None:
        if not isinstance(chunk_size, int) or isinstance(chunk_size, bool) or chunk_size < 1:
            raise ValueError("chunk_size must be a positive integer")
        self._repository = repository or InMemorySnapshotRepository()
        self._default_key = default_encryption_key
        self._chunk_size = chunk_size

    @property
    def repository(self) -> SnapshotRepository:
        return self._repository

    async def capture(
        self,
        tenant_id: str,
        data: bytes | str,
        metadata: dict[str, Any] | None = None,
        retention_policy: RetentionPolicy = RetentionPolicy.KEEP_ALL,
        retention_params: dict[str, Any] | None = None,
        encryption_key: bytes | None = None,
        verify: bool = True,
    ) -> SnapshotRecord:
        """Capture a full snapshot of the given data."""
        tenant_id = _validate_tenant_id(tenant_id)
        payload = _as_bytes(data)
        key = encryption_key if encryption_key is not None else self._default_key
        snapshot = SnapshotRecord.create_full(
            tenant_id=tenant_id,
            data=payload,
            metadata=metadata,
            retention_policy=retention_policy,
            retention_params=retention_params,
            encryption_key=key,
            chunk_size=self._chunk_size,
        )
        if verify:
            snapshot = snapshot.mark_verified(key)
        return await self._repository.save(snapshot)

    async def capture_incremental(
        self,
        tenant_id: str,
        data: bytes | str,
        base_snapshot_id: str,
        metadata: dict[str, Any] | None = None,
        retention_policy: RetentionPolicy = RetentionPolicy.KEEP_ALL,
        retention_params: dict[str, Any] | None = None,
        encryption_key: bytes | None = None,
        verify: bool = True,
    ) -> SnapshotRecord:
        """Capture an incremental snapshot against a base snapshot."""
        tenant_id = _validate_tenant_id(tenant_id)
        payload = _as_bytes(data)
        key = encryption_key if encryption_key is not None else self._default_key
        base_snapshot = await self._repository.get(tenant_id, base_snapshot_id)
        if base_snapshot is None:
            raise ValueError(f"Base snapshot {base_snapshot_id} not found for tenant {tenant_id}")
        base_data = await self._reconstruct_lineage(tenant_id, base_snapshot.snapshot_id, key)
        snapshot = SnapshotRecord.create_incremental(
            tenant_id=tenant_id,
            data=payload,
            base_snapshot=base_snapshot,
            metadata=metadata,
            retention_policy=retention_policy,
            retention_params=retention_params,
            encryption_key=key,
            chunk_size=self._chunk_size,
            base_data=base_data,
        )
        if verify:
            snapshot = snapshot.mark_verified(key, base_data=base_data)
        return await self._repository.save(snapshot)

    async def get(
        self,
        tenant_id: str,
        snapshot_id: str,
        encryption_key: bytes | None = None,
        verify_integrity: bool = True,
    ) -> SnapshotRecord | None:
        """Get a snapshot by ID. Returns encrypted record; use reconstruct() for plaintext."""
        tenant_id = _validate_tenant_id(tenant_id)
        snapshot = await self._repository.get(tenant_id, snapshot_id)
        if snapshot is None:
            return None
        if verify_integrity:
            key = encryption_key if encryption_key is not None else self._default_key
            ok, message = await self._verify_lineage(tenant_id, snapshot_id, key)
            if not ok:
                raise ValueError(f"Snapshot integrity check failed: {message}")
        return snapshot

    async def reconstruct(
        self,
        tenant_id: str,
        snapshot_id: str,
        encryption_key: bytes | None = None,
    ) -> bytes:
        """Reconstruct full plaintext data from a snapshot."""
        tenant_id = _validate_tenant_id(tenant_id)
        snapshot = await self.get(tenant_id, snapshot_id, encryption_key, verify_integrity=True)
        if snapshot is None:
            raise ValueError(f"Snapshot {snapshot_id} not found")
        key = encryption_key if encryption_key is not None else self._default_key
        return await self._reconstruct_lineage(tenant_id, snapshot_id, key)

    async def reconstruct_from_chain(
        self,
        tenant_id: str,
        snapshot_id: str,
        encryption_key: bytes | None = None,
    ) -> bytes:
        """Reconstruct by walking and authenticating the full lineage chain."""
        tenant_id = _validate_tenant_id(tenant_id)
        key = encryption_key if encryption_key is not None else self._default_key
        ok, message = await self._verify_lineage(tenant_id, snapshot_id, key)
        if not ok:
            raise ValueError(f"Snapshot lineage verification failed: {message}")
        return await self._reconstruct_lineage(tenant_id, snapshot_id, key)

    async def _reconstruct_lineage(
        self, tenant_id: str, snapshot_id: str, key: bytes | None
    ) -> bytes:
        lineage = await self._repository.get_lineage(tenant_id, snapshot_id)
        if not lineage:
            raise ValueError(f"No lineage found for snapshot {snapshot_id}")
        if lineage[-1].snapshot_id != snapshot_id:
            raise ValueError(f"Lineage for snapshot {snapshot_id} is incomplete")

        result: bytes | None = None
        previous: SnapshotRecord | None = None
        for snapshot in lineage:
            if snapshot.tenant_id != tenant_id:
                raise ValueError("Snapshot lineage crossed tenant scope")
            if previous is not None and snapshot.parent_snapshot_id != previous.snapshot_id:
                raise ValueError("Snapshot lineage parent relationship is invalid")
            if snapshot.snapshot_type == SnapshotType.FULL:
                result = snapshot.reconstruct(key)
            elif snapshot.snapshot_type == SnapshotType.INCREMENTAL:
                if result is None:
                    raise ValueError("Incremental lineage has no full base")
                delta = _decode_delta(snapshot.chunks, key)
                result = apply_delta(result, delta)
            else:
                raise ValueError(f"Unsupported snapshot type: {snapshot.snapshot_type!r}")
            previous = snapshot

        if result is None:
            raise ValueError("Snapshot lineage did not produce data")
        return result

    async def _verify_lineage(
        self, tenant_id: str, snapshot_id: str, key: bytes | None
    ) -> tuple[bool, str]:
        try:
            lineage = await self._repository.get_lineage(tenant_id, snapshot_id)
            if not lineage:
                return False, "No lineage found"
            if lineage[-1].snapshot_id != snapshot_id:
                return False, "Lineage is incomplete"

            result: bytes | None = None
            previous: SnapshotRecord | None = None
            root_id = lineage[0].snapshot_id
            for snapshot in lineage:
                if snapshot.tenant_id != tenant_id:
                    return False, "Lineage crossed tenant scope"
                if previous is not None and snapshot.parent_snapshot_id != previous.snapshot_id:
                    return False, "Lineage parent relationship is invalid"
                if snapshot.snapshot_type == SnapshotType.FULL:
                    ok, message = snapshot.verify_integrity(key)
                    if not ok:
                        return False, message
                    result = snapshot.reconstruct(key)
                elif snapshot.snapshot_type == SnapshotType.INCREMENTAL:
                    if result is None:
                        return False, "Incremental lineage has no full base"
                    if snapshot.base_snapshot_id != root_id:
                        return False, "Incremental base lineage is invalid"
                    ok, message = snapshot.verify_integrity(key, base_data=result)
                    if not ok:
                        return False, message
                    delta = _decode_delta(snapshot.chunks, key)
                    result = apply_delta(result, delta)
                    if snapshot.verification_hash:
                        verification = hashlib.sha256(result).hexdigest()
                        if verification != snapshot.verification_hash:
                            return (
                                False,
                                f"Data verification hash mismatch for {snapshot.snapshot_id}",
                            )
                else:
                    return False, f"Unsupported snapshot type: {snapshot.snapshot_type!r}"
                previous = snapshot
            return True, "OK"
        except Exception as exc:
            return False, str(exc)

    async def verify(
        self,
        tenant_id: str,
        snapshot_id: str,
        encryption_key: bytes | None = None,
    ) -> tuple[bool, str]:
        """Verify snapshot integrity and tamper detection."""
        tenant_id = _validate_tenant_id(tenant_id)
        snapshot = await self._repository.get(tenant_id, snapshot_id)
        if snapshot is None:
            return False, f"Snapshot {snapshot_id} not found"
        key = encryption_key if encryption_key is not None else self._default_key
        return await self._verify_lineage(tenant_id, snapshot_id, key)

    async def verify_all(
        self,
        tenant_id: str,
        encryption_key: bytes | None = None,
    ) -> list[tuple[str, bool, str]]:
        """Verify all snapshots for a tenant."""
        tenant_id = _validate_tenant_id(tenant_id)
        snapshots = await self._repository.list_snapshots(tenant_id, limit=10000)
        key = encryption_key if encryption_key is not None else self._default_key
        results: list[tuple[str, bool, str]] = []
        for snapshot in snapshots:
            ok, message = await self._verify_lineage(tenant_id, snapshot.snapshot_id, key)
            results.append((snapshot.snapshot_id, ok, message))
        return results

    async def delete_expired(
        self,
        tenant_id: str,
        now: datetime | None = None,
    ) -> int:
        """Delete snapshots expired by their retention policy."""
        tenant_id = _validate_tenant_id(tenant_id)
        return await self._repository.delete_expired(tenant_id, now)

    async def readiness(
        self,
        tenant_id: str,
        encryption_key: bytes | None = None,
        max_age_seconds: float = 86400,
    ) -> SnapshotReadiness:
        """Assess recovery readiness for a tenant."""
        tenant_id = _validate_tenant_id(tenant_id)
        key = encryption_key if encryption_key is not None else self._default_key
        try:
            snapshots = await self._repository.list_snapshots(tenant_id, limit=10000)
        except Exception as exc:
            return SnapshotReadiness(
                tenant_id=tenant_id,
                ready=False,
                latest_snapshot_id=None,
                latest_snapshot_age_seconds=0.0,
                total_snapshots=0,
                total_size_bytes=0,
                expired_snapshots=0,
                unverified_snapshots=0,
                lineage_depth_max=0,
                storage_healthy=False,
                issues=[f"Snapshot storage unavailable: {exc}"],
                recommendations=["Repair snapshot storage"],
            )

        snapshots.sort(key=lambda item: (item.created_at, item.snapshot_id), reverse=True)
        storage_errors = [
            str(error)
            for error in getattr(self._repository, "_storage_errors", {}).get(tenant_id, [])
        ]

        if not snapshots:
            return SnapshotReadiness(
                tenant_id=tenant_id,
                ready=False,
                latest_snapshot_id=None,
                latest_snapshot_age_seconds=0.0,
                total_snapshots=0,
                total_size_bytes=0,
                expired_snapshots=0,
                unverified_snapshots=0,
                lineage_depth_max=0,
                storage_healthy=not storage_errors,
                issues=(
                    ["No snapshots found"]
                    if not storage_errors
                    else [
                        "Snapshot storage contains unreadable records: " + "; ".join(storage_errors)
                    ]
                ),
                recommendations=["Capture initial snapshot"],
            )

        now = datetime.now(UTC)
        latest = snapshots[0]
        latest_created_at = _as_utc(latest.created_at)
        latest_age = (now - latest_created_at).total_seconds()
        expired = sum(1 for snapshot in snapshots if snapshot.is_expired(now))
        failed: dict[str, str] = {}
        depths: list[int] = []

        for snapshot in snapshots:
            try:
                lineage = await self._repository.get_lineage(tenant_id, snapshot.snapshot_id)
                depths.append(max(0, len(lineage) - 1))
            except Exception as exc:
                failed[snapshot.snapshot_id] = f"Lineage unavailable: {exc}"
                continue
            ok, message = await self._verify_lineage(tenant_id, snapshot.snapshot_id, key)
            if not ok:
                failed[snapshot.snapshot_id] = message

        if storage_errors:
            failed["<storage>"] = "; ".join(storage_errors)

        unverified_ids = {
            snapshot.snapshot_id for snapshot in snapshots if not snapshot.is_verified
        }
        unverified_ids.update(failed.keys())
        max_depth = max(depths, default=0)
        issues: list[str] = []
        recommendations: list[str] = []

        def add_issue(issue: str, recommendation: str) -> None:
            issues.append(issue)
            if recommendation not in recommendations:
                recommendations.append(recommendation)

        if latest_age > max_age_seconds:
            add_issue(
                f"Latest snapshot is {latest_age:.0f}s old (max {max_age_seconds}s)",
                "Capture new snapshot",
            )
        if latest_age < 0:
            add_issue(
                "Latest snapshot timestamp is in the future", "Check snapshot clock synchronization"
            )
        if expired:
            add_issue(f"{expired} expired snapshots", "Run delete_expired cleanup")
        if unverified_ids:
            add_issue(
                f"{len(unverified_ids)} unverified snapshots", "Run verification on all snapshots"
            )
        if failed:
            add_issue(
                f"{len(failed)} snapshots failed integrity or lineage verification",
                "Repair or recapture affected snapshots",
            )
        if max_depth > 10:
            add_issue(
                f"Lineage depth {max_depth} exceeds recommended maximum of 10",
                "Consider new full snapshot baseline",
            )

        storage_healthy = not failed
        return SnapshotReadiness(
            tenant_id=tenant_id,
            ready=storage_healthy and not issues,
            latest_snapshot_id=latest.snapshot_id,
            latest_snapshot_age_seconds=latest_age,
            total_snapshots=len(snapshots),
            total_size_bytes=sum(snapshot.total_size for snapshot in snapshots),
            expired_snapshots=expired,
            unverified_snapshots=len(unverified_ids),
            lineage_depth_max=max_depth,
            storage_healthy=storage_healthy,
            issues=issues,
            recommendations=recommendations,
        )

    async def list_snapshots(
        self,
        tenant_id: str,
        snapshot_type: SnapshotType | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SnapshotRecord]:
        tenant_id = _validate_tenant_id(tenant_id)
        return await self._repository.list_snapshots(tenant_id, snapshot_type, limit, offset)

    async def get_lineage(
        self,
        tenant_id: str,
        snapshot_id: str,
    ) -> list[SnapshotRecord]:
        tenant_id = _validate_tenant_id(tenant_id)
        return await self._repository.get_lineage(tenant_id, snapshot_id)

    async def deduplicate_chunks(
        self,
        tenant_id: str,
        snapshot_id: str,
    ) -> int:
        """Identify duplicate content-addressed chunks within a snapshot."""
        tenant_id = _validate_tenant_id(tenant_id)
        snapshot = await self._repository.get(tenant_id, snapshot_id)
        if snapshot is None:
            return 0
        seen: set[str] = set()
        duplicates = 0
        for chunk in snapshot.chunks:
            if chunk.content_hash in seen:
                duplicates += 1
            else:
                seen.add(chunk.content_hash)
        return duplicates
