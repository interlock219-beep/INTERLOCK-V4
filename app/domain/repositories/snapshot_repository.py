from __future__ import annotations

import hashlib
import json
import shutil
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.domain.entities.snapshot_types import (
    CompressionAlgorithm,
    EncryptionAlgorithm,
    RetentionPolicy,
    SnapshotChunk,
    SnapshotRecord,
    SnapshotType,
)


def _validate_tenant_id(tenant_id: str) -> str:
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise ValueError("tenant_id must be a non-empty string")
    return tenant_id


def _validate_snapshot_id(snapshot_id: str) -> str:
    if not isinstance(snapshot_id, str) or not snapshot_id.strip():
        raise ValueError("snapshot_id must be a non-empty string")
    return snapshot_id


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _retention_days(params: dict[str, Any]) -> int | float:
    value = params.get("days", params.get("within_days", params.get("retention_days", 30)))
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("retention days must be a non-negative number")
    if value < 0:
        raise ValueError("retention days must be a non-negative number")
    return value


def _retention_count(params: dict[str, Any]) -> int:
    value = params.get(
        "count",
        params.get("n", params.get("keep", params.get("keep_last_n", params.get("retain", 1)))),
    )
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("retention count must be a positive integer")
    return value


def _time_expired(snapshot: SnapshotRecord, now: datetime) -> bool:
    if snapshot.expires_at is not None:
        return _as_utc(now) >= _as_utc(snapshot.expires_at)
    if snapshot.retention_policy in {
        RetentionPolicy.KEEP_WITHIN_DAYS,
        RetentionPolicy.KEEP_LAST_N_WITHIN_DAYS,
    }:
        try:
            return _as_utc(now) >= _as_utc(snapshot.created_at) + timedelta(
                days=_retention_days(snapshot.retention_params)
            )
        except (TypeError, ValueError):
            return False
    return False


def _retention_candidates(snapshots: list[SnapshotRecord], now: datetime) -> list[str]:
    ordered = sorted(snapshots, key=lambda item: (item.created_at, item.snapshot_id), reverse=True)
    candidates: set[str] = set()
    for snapshot in ordered:
        if _time_expired(snapshot, now):
            candidates.add(snapshot.snapshot_id)

    grouped: dict[tuple[str, str], list[SnapshotRecord]] = {}
    for snapshot in ordered:
        if snapshot.retention_policy in {
            RetentionPolicy.KEEP_LAST_N,
            RetentionPolicy.KEEP_LAST_N_WITHIN_DAYS,
        }:
            key = (snapshot.retention_policy.value, repr(snapshot.retention_params))
            grouped.setdefault(key, []).append(snapshot)

    for group in grouped.values():
        try:
            keep_count = _retention_count(group[0].retention_params)
        except (TypeError, ValueError):
            continue
        for snapshot in group[keep_count:]:
            candidates.add(snapshot.snapshot_id)

    retained = {snapshot.snapshot_id for snapshot in ordered} - candidates
    while True:
        required_parents = {
            snapshot.parent_snapshot_id
            for snapshot in snapshots
            if snapshot.snapshot_id in retained and snapshot.parent_snapshot_id is not None
        }
        protected = candidates & required_parents
        if not protected:
            break
        candidates.difference_update(protected)

    ordered_ids = {snapshot.snapshot_id: index for index, snapshot in enumerate(ordered)}
    return sorted(candidates, key=lambda snapshot_id: ordered_ids[snapshot_id])


class SnapshotRepository(ABC):
    """Abstract repository for tenant-scoped snapshot persistence."""

    @abstractmethod
    async def save(self, snapshot: SnapshotRecord) -> SnapshotRecord: ...

    @abstractmethod
    async def get(self, tenant_id: str, snapshot_id: str) -> SnapshotRecord | None: ...

    @abstractmethod
    async def get_by_content_hash(
        self, tenant_id: str, content_hash: str
    ) -> SnapshotRecord | None: ...

    @abstractmethod
    async def list_snapshots(
        self,
        tenant_id: str,
        snapshot_type: SnapshotType | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SnapshotRecord]: ...

    @abstractmethod
    async def delete(self, tenant_id: str, snapshot_id: str) -> bool: ...

    @abstractmethod
    async def delete_expired(self, tenant_id: str, now: datetime | None = None) -> int: ...

    @abstractmethod
    async def get_lineage(self, tenant_id: str, snapshot_id: str) -> list[SnapshotRecord]: ...

    @abstractmethod
    async def get_chunks(self, tenant_id: str, snapshot_id: str) -> list[SnapshotChunk]: ...


class InMemorySnapshotRepository(SnapshotRepository):
    """In-memory snapshot repository for testing."""

    def __init__(self) -> None:
        self._snapshots: dict[str, dict[str, SnapshotRecord]] = {}
        self._chunks: dict[str, dict[str, list[SnapshotChunk]]] = {}

    @staticmethod
    def _validate_scope(snapshot: SnapshotRecord) -> None:
        _validate_tenant_id(snapshot.tenant_id)
        _validate_snapshot_id(snapshot.snapshot_id)
        if snapshot.chunk_count != len(snapshot.chunks):
            raise ValueError("Snapshot chunk count mismatch")
        if any(
            chunk.tenant_id != snapshot.tenant_id or chunk.snapshot_id != snapshot.snapshot_id
            for chunk in snapshot.chunks
        ):
            raise ValueError("Snapshot chunks must remain in their snapshot tenant scope")

    async def save(self, snapshot: SnapshotRecord) -> SnapshotRecord:
        self._validate_scope(snapshot)
        tenant_snapshots = self._snapshots.setdefault(snapshot.tenant_id, {})
        tenant_snapshots[snapshot.snapshot_id] = snapshot
        tenant_chunks = self._chunks.setdefault(snapshot.tenant_id, {})
        tenant_chunks[snapshot.snapshot_id] = list(snapshot.chunks)
        return snapshot

    async def get(self, tenant_id: str, snapshot_id: str) -> SnapshotRecord | None:
        _validate_tenant_id(tenant_id)
        _validate_snapshot_id(snapshot_id)
        return self._snapshots.get(tenant_id, {}).get(snapshot_id)

    async def get_by_content_hash(self, tenant_id: str, content_hash: str) -> SnapshotRecord | None:
        _validate_tenant_id(tenant_id)
        for snapshot in self._snapshots.get(tenant_id, {}).values():
            if snapshot.content_hash == content_hash:
                return snapshot
        return None

    async def list_snapshots(
        self,
        tenant_id: str,
        snapshot_type: SnapshotType | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SnapshotRecord]:
        _validate_tenant_id(tenant_id)
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
            raise ValueError("limit must be a non-negative integer")
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            raise ValueError("offset must be a non-negative integer")
        snapshots = list(self._snapshots.get(tenant_id, {}).values())
        if snapshot_type is not None:
            try:
                expected_type = SnapshotType(snapshot_type)
            except (TypeError, ValueError):
                return []
            snapshots = [
                snapshot for snapshot in snapshots if snapshot.snapshot_type == expected_type
            ]
        snapshots.sort(key=lambda item: (item.created_at, item.snapshot_id), reverse=True)
        return snapshots[offset : offset + limit]

    async def delete(self, tenant_id: str, snapshot_id: str) -> bool:
        _validate_tenant_id(tenant_id)
        _validate_snapshot_id(snapshot_id)
        if snapshot_id not in self._snapshots.get(tenant_id, {}):
            return False
        del self._snapshots[tenant_id][snapshot_id]
        self._chunks.get(tenant_id, {}).pop(snapshot_id, None)
        return True

    async def delete_expired(self, tenant_id: str, now: datetime | None = None) -> int:
        _validate_tenant_id(tenant_id)
        check_time = _as_utc(now or datetime.now(UTC))
        snapshots = list(self._snapshots.get(tenant_id, {}).values())
        candidates = _retention_candidates(snapshots, check_time)
        for snapshot_id in candidates:
            await self.delete(tenant_id, snapshot_id)
        return len(candidates)

    async def get_lineage(self, tenant_id: str, snapshot_id: str) -> list[SnapshotRecord]:
        _validate_tenant_id(tenant_id)
        _validate_snapshot_id(snapshot_id)
        snapshot = await self.get(tenant_id, snapshot_id)
        if snapshot is None:
            return []
        lineage: list[SnapshotRecord] = []
        current = snapshot
        visited: set[str] = set()
        while current.parent_snapshot_id:
            if current.snapshot_id in visited:
                raise ValueError("Snapshot lineage contains a cycle")
            visited.add(current.snapshot_id)
            parent = await self.get(tenant_id, current.parent_snapshot_id)
            if parent is None:
                break
            lineage.append(parent)
            current = parent
        return list(reversed(lineage)) + [snapshot]

    async def get_chunks(self, tenant_id: str, snapshot_id: str) -> list[SnapshotChunk]:
        _validate_tenant_id(tenant_id)
        _validate_snapshot_id(snapshot_id)
        return list(self._chunks.get(tenant_id, {}).get(snapshot_id, []))


class FilesystemSnapshotRepository(SnapshotRepository):
    """Path-safe filesystem snapshot repository."""

    def __init__(self, base_path: str | Path) -> None:
        self._base_path = Path(base_path).resolve()
        self._base_path.mkdir(parents=True, exist_ok=True)
        self._storage_errors: dict[str, list[str]] = {}

    def _record_storage_error(self, tenant_id: str, error: object) -> None:
        message = str(error)
        errors = self._storage_errors.setdefault(tenant_id, [])
        if message not in errors:
            errors.append(message)

    def _ensure_within_base(self, path: Path) -> Path:
        resolved = path.resolve()
        if resolved != self._base_path and self._base_path not in resolved.parents:
            raise ValueError("Snapshot path escapes repository base")
        return resolved

    def _tenant_path(self, tenant_id: str) -> Path:
        tenant_id = _validate_tenant_id(tenant_id)
        tenant_dir = self._base_path / hashlib.sha256(tenant_id.encode()).hexdigest()
        tenant_dir.mkdir(parents=True, exist_ok=True)
        return self._ensure_within_base(tenant_dir)

    def _snapshot_path(self, tenant_id: str, snapshot_id: str) -> Path:
        snapshot_id = _validate_snapshot_id(snapshot_id)
        tenant_dir = self._tenant_path(tenant_id)
        safe_sid = hashlib.sha256(snapshot_id.encode()).hexdigest()
        return self._ensure_within_base(tenant_dir / f"{safe_sid}.json")

    def _chunks_dir(self, tenant_id: str, snapshot_id: str) -> Path:
        snapshot_id = _validate_snapshot_id(snapshot_id)
        tenant_dir = self._tenant_path(tenant_id)
        safe_sid = hashlib.sha256(snapshot_id.encode()).hexdigest()
        chunks_dir = tenant_dir / f"{safe_sid}_chunks"
        chunks_dir.mkdir(parents=True, exist_ok=True)
        return self._ensure_within_base(chunks_dir)

    def _serialize_chunk(self, chunk: SnapshotChunk) -> dict[str, Any]:
        return {
            "chunk_id": chunk.chunk_id,
            "tenant_id": chunk.tenant_id,
            "snapshot_id": chunk.snapshot_id,
            "sequence": chunk.sequence,
            "data": chunk.data.hex(),
            "content_hash": chunk.content_hash,
            "compressed_size": chunk.compressed_size,
            "original_size": chunk.original_size,
            "compression": chunk.compression.value,
            "encryption": chunk.encryption.value,
            "nonce": chunk.nonce.hex(),
            "auth_tag": chunk.auth_tag.hex(),
            "created_at": chunk.created_at.isoformat(),
        }

    def _deserialize_chunk(
        self,
        data: dict[str, Any],
        expected_tenant: str | None = None,
        expected_snapshot: str | None = None,
    ) -> SnapshotChunk:
        chunk = SnapshotChunk(
            chunk_id=data["chunk_id"],
            tenant_id=data["tenant_id"],
            snapshot_id=data["snapshot_id"],
            sequence=data["sequence"],
            data=bytes.fromhex(data["data"]),
            content_hash=data["content_hash"],
            compressed_size=data["compressed_size"],
            original_size=data["original_size"],
            compression=CompressionAlgorithm(data["compression"]),
            encryption=EncryptionAlgorithm(data["encryption"]),
            nonce=bytes.fromhex(data["nonce"]),
            auth_tag=bytes.fromhex(data["auth_tag"]),
            created_at=_as_utc(datetime.fromisoformat(data["created_at"])),
        )
        if expected_tenant is not None and chunk.tenant_id != expected_tenant:
            raise ValueError("Chunk tenant scope mismatch")
        if expected_snapshot is not None and chunk.snapshot_id != expected_snapshot:
            raise ValueError("Chunk snapshot scope mismatch")
        return chunk

    def _serialize_snapshot(self, snapshot: SnapshotRecord) -> dict[str, Any]:
        return {
            "snapshot_id": snapshot.snapshot_id,
            "tenant_id": snapshot.tenant_id,
            "snapshot_type": snapshot.snapshot_type.value,
            "parent_snapshot_id": snapshot.parent_snapshot_id,
            "base_snapshot_id": snapshot.base_snapshot_id,
            "content_hash": snapshot.content_hash,
            "total_size": snapshot.total_size,
            "chunk_count": snapshot.chunk_count,
            "metadata": snapshot.metadata,
            "retention_policy": snapshot.retention_policy.value,
            "retention_params": snapshot.retention_params,
            "created_at": snapshot.created_at.isoformat(),
            "expires_at": snapshot.expires_at.isoformat() if snapshot.expires_at else None,
            "lineage_depth": snapshot.lineage_depth,
            "is_verified": snapshot.is_verified,
            "verification_hash": snapshot.verification_hash,
        }

    def _deserialize_snapshot(
        self,
        data: dict[str, Any],
        chunks: list[SnapshotChunk],
        expected_tenant: str,
        expected_snapshot: str,
    ) -> SnapshotRecord:
        if data["tenant_id"] != expected_tenant or data["snapshot_id"] != expected_snapshot:
            raise ValueError("Snapshot metadata scope mismatch")
        if data["chunk_count"] != len(chunks):
            raise ValueError("Snapshot chunk count mismatch")
        if any(
            chunk.tenant_id != expected_tenant or chunk.snapshot_id != expected_snapshot
            for chunk in chunks
        ):
            raise ValueError("Snapshot chunk scope mismatch")
        return SnapshotRecord(
            snapshot_id=data["snapshot_id"],
            tenant_id=data["tenant_id"],
            snapshot_type=SnapshotType(data["snapshot_type"]),
            parent_snapshot_id=data["parent_snapshot_id"],
            base_snapshot_id=data["base_snapshot_id"],
            content_hash=data["content_hash"],
            total_size=data["total_size"],
            chunk_count=data["chunk_count"],
            chunks=tuple(chunks),
            metadata=data["metadata"],
            retention_policy=RetentionPolicy(data["retention_policy"]),
            retention_params=data["retention_params"],
            created_at=_as_utc(datetime.fromisoformat(data["created_at"])),
            expires_at=_as_utc(datetime.fromisoformat(data["expires_at"]))
            if data["expires_at"]
            else None,
            lineage_depth=data["lineage_depth"],
            is_verified=data["is_verified"],
            verification_hash=data["verification_hash"],
        )

    @staticmethod
    def _validate_scope(snapshot: SnapshotRecord) -> None:
        _validate_tenant_id(snapshot.tenant_id)
        _validate_snapshot_id(snapshot.snapshot_id)
        if snapshot.chunk_count != len(snapshot.chunks):
            raise ValueError("Snapshot chunk count mismatch")
        if any(
            chunk.tenant_id != snapshot.tenant_id or chunk.snapshot_id != snapshot.snapshot_id
            for chunk in snapshot.chunks
        ):
            raise ValueError("Snapshot chunks must remain in their snapshot tenant scope")

    async def save(self, snapshot: SnapshotRecord) -> SnapshotRecord:
        self._validate_scope(snapshot)
        snapshot_file = self._snapshot_path(snapshot.tenant_id, snapshot.snapshot_id)
        chunks_dir = self._chunks_dir(snapshot.tenant_id, snapshot.snapshot_id)
        expected_files = {f"{chunk.sequence:06d}.chunk" for chunk in snapshot.chunks}
        for existing in chunks_dir.glob("*.chunk"):
            if existing.name not in expected_files:
                existing.unlink()
        for chunk in snapshot.chunks:
            chunk_file = chunks_dir / f"{chunk.sequence:06d}.chunk"
            chunk_file.write_bytes(
                json.dumps(self._serialize_chunk(chunk), sort_keys=True).encode("utf-8")
            )
        snapshot_file.write_bytes(
            json.dumps(self._serialize_snapshot(snapshot), sort_keys=True).encode("utf-8")
        )
        return snapshot

    async def get(self, tenant_id: str, snapshot_id: str) -> SnapshotRecord | None:
        _validate_tenant_id(tenant_id)
        _validate_snapshot_id(snapshot_id)
        snapshot_file = self._snapshot_path(tenant_id, snapshot_id)
        if not snapshot_file.exists():
            return None
        try:
            data = json.loads(snapshot_file.read_bytes())
            chunks = await self.get_chunks(tenant_id, snapshot_id)
            return self._deserialize_snapshot(data, chunks, tenant_id, snapshot_id)
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            self._record_storage_error(tenant_id, f"get {tenant_id}/{snapshot_id}: {exc}")
            return None

    async def get_by_content_hash(self, tenant_id: str, content_hash: str) -> SnapshotRecord | None:
        _validate_tenant_id(tenant_id)
        tenant_dir = self._tenant_path(tenant_id)
        for snapshot_file in tenant_dir.glob("*.json"):
            try:
                data = json.loads(snapshot_file.read_bytes())
                if data.get("tenant_id") != tenant_id or data.get("content_hash") != content_hash:
                    continue
                snapshot_id = data["snapshot_id"]
                chunks = await self.get_chunks(tenant_id, snapshot_id)
                return self._deserialize_snapshot(data, chunks, tenant_id, snapshot_id)
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                self._record_storage_error(tenant_id, f"get_by_content_hash {tenant_id}: {exc}")
                continue
        return None

    async def list_snapshots(
        self,
        tenant_id: str,
        snapshot_type: SnapshotType | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SnapshotRecord]:
        _validate_tenant_id(tenant_id)
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
            raise ValueError("limit must be a non-negative integer")
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            raise ValueError("offset must be a non-negative integer")
        try:
            expected_type = SnapshotType(snapshot_type) if snapshot_type is not None else None
        except (TypeError, ValueError):
            return []
        tenant_dir = self._tenant_path(tenant_id)
        snapshots: list[SnapshotRecord] = []
        for snapshot_file in tenant_dir.glob("*.json"):
            try:
                data = json.loads(snapshot_file.read_bytes())
                if expected_type is not None and data.get("snapshot_type") != expected_type.value:
                    continue
                snapshot_id = data["snapshot_id"]
                chunks = await self.get_chunks(tenant_id, snapshot_id)
                snapshots.append(self._deserialize_snapshot(data, chunks, tenant_id, snapshot_id))
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                self._record_storage_error(tenant_id, f"list_snapshots {tenant_id}: {exc}")
                continue
        snapshots.sort(key=lambda item: (item.created_at, item.snapshot_id), reverse=True)
        return snapshots[offset : offset + limit]

    async def delete(self, tenant_id: str, snapshot_id: str) -> bool:
        _validate_tenant_id(tenant_id)
        _validate_snapshot_id(snapshot_id)
        snapshot_file = self._snapshot_path(tenant_id, snapshot_id)
        chunks_dir = self._chunks_dir(tenant_id, snapshot_id)
        if not snapshot_file.exists():
            return False
        snapshot_file.unlink()
        if chunks_dir.exists():
            shutil.rmtree(chunks_dir)
        return True

    async def delete_expired(self, tenant_id: str, now: datetime | None = None) -> int:
        _validate_tenant_id(tenant_id)
        check_time = _as_utc(now or datetime.now(UTC))
        snapshots = await self.list_snapshots(tenant_id, limit=10000)
        candidates = _retention_candidates(snapshots, check_time)
        deleted = 0
        for snapshot_id in candidates:
            if await self.delete(tenant_id, snapshot_id):
                deleted += 1
        return deleted

    async def get_lineage(self, tenant_id: str, snapshot_id: str) -> list[SnapshotRecord]:
        _validate_tenant_id(tenant_id)
        _validate_snapshot_id(snapshot_id)
        snapshot = await self.get(tenant_id, snapshot_id)
        if snapshot is None:
            return []
        lineage: list[SnapshotRecord] = []
        current = snapshot
        visited: set[str] = set()
        while current.parent_snapshot_id:
            if current.snapshot_id in visited:
                raise ValueError("Snapshot lineage contains a cycle")
            visited.add(current.snapshot_id)
            parent = await self.get(tenant_id, current.parent_snapshot_id)
            if parent is None:
                break
            lineage.append(parent)
            current = parent
        return list(reversed(lineage)) + [snapshot]

    async def get_chunks(self, tenant_id: str, snapshot_id: str) -> list[SnapshotChunk]:
        _validate_tenant_id(tenant_id)
        _validate_snapshot_id(snapshot_id)
        chunks_dir = self._chunks_dir(tenant_id, snapshot_id)
        if not chunks_dir.exists():
            return []
        chunks: list[SnapshotChunk] = []
        for chunk_file in sorted(chunks_dir.glob("*.chunk")):
            try:
                data = json.loads(chunk_file.read_bytes())
                chunks.append(self._deserialize_chunk(data, tenant_id, snapshot_id))
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                self._record_storage_error(
                    tenant_id, f"get_chunks {tenant_id}/{snapshot_id}: {exc}"
                )
                continue
        chunks.sort(key=lambda chunk: chunk.sequence)
        return chunks
