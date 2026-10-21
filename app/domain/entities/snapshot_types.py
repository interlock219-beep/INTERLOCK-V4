from __future__ import annotations

import hashlib
import math
import secrets
import struct
import zlib
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, TypeVar

_DELTA_MAGIC = b"INTERLOCK-SNAPSHOT-DELTA-V1\x00"


class SnapshotType(StrEnum):
    FULL = "full"
    INCREMENTAL = "incremental"


class CompressionAlgorithm(StrEnum):
    NONE = "none"
    ZLIB = "zlib"


class EncryptionAlgorithm(StrEnum):
    NONE = "none"
    AES_256_GCM = "aes_256_gcm"


class RetentionPolicy(StrEnum):
    KEEP_ALL = "keep_all"
    KEEP_LAST_N = "keep_last_n"
    KEEP_WITHIN_DAYS = "keep_within_days"
    KEEP_LAST_N_WITHIN_DAYS = "keep_last_n_within_days"


def _as_bytes(value: bytes | bytearray | memoryview | str, name: str = "data") -> bytes:
    if isinstance(value, str):
        return value.encode()
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value)
    raise TypeError(f"{name} must be bytes-like or str")


def _validate_identifier(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _validate_aes_key(key: bytes | None) -> bytes:
    if not isinstance(key, bytes):
        raise TypeError("AES-256-GCM key must be bytes")
    if len(key) != 32:
        raise ValueError("AES-256-GCM requires a 32-byte key")
    return key


EnumT = TypeVar("EnumT", bound=StrEnum)


def _coerce_enum(value: Any, enum_type: type[EnumT], name: str) -> EnumT:
    try:
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {name}: {value!r}") from exc


def _retention_days(params: dict[str, Any]) -> int | float:
    value = params.get("days", params.get("within_days", params.get("retention_days", 30)))
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("retention days must be a non-negative number")
    if not math.isfinite(float(value)) or value < 0:
        raise ValueError("retention days must be a non-negative number")
    days: int | float = value
    return days


def _retention_count(params: dict[str, Any]) -> int:
    value = params.get(
        "count",
        params.get("n", params.get("keep", params.get("keep_last_n", params.get("retain", 1)))),
    )
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("retention count must be a positive integer")
    count: int = value
    return count


def _normalise_retention(
    policy: RetentionPolicy | str,
    params: dict[str, Any] | None,
) -> tuple[RetentionPolicy, dict[str, Any]]:
    normalised_policy = _coerce_enum(policy, RetentionPolicy, "retention policy")
    normalised_params = dict(params or {})
    if normalised_policy == RetentionPolicy.KEEP_WITHIN_DAYS:
        _retention_days(normalised_params)
    elif normalised_policy == RetentionPolicy.KEEP_LAST_N:
        _retention_count(normalised_params)
    elif normalised_policy == RetentionPolicy.KEEP_LAST_N_WITHIN_DAYS:
        _retention_days(normalised_params)
        _retention_count(normalised_params)
    return normalised_policy, normalised_params


def _retention_expires_at(
    policy: RetentionPolicy,
    params: dict[str, Any],
    created_at: datetime,
) -> datetime | None:
    if policy not in {RetentionPolicy.KEEP_WITHIN_DAYS, RetentionPolicy.KEEP_LAST_N_WITHIN_DAYS}:
        return None
    return created_at + timedelta(days=_retention_days(params))


def _chunk_chain_hash(chunks: tuple[SnapshotChunk, ...] | list[SnapshotChunk]) -> str:
    return hashlib.sha256(
        b"".join(chunk.content_hash.encode("ascii") for chunk in chunks)
    ).hexdigest()


def _decode_chunks(chunks: tuple[SnapshotChunk, ...], key: bytes | None) -> bytes:
    expected_sequences = list(range(len(chunks)))
    actual_sequences = [chunk.sequence for chunk in chunks]
    if actual_sequences != expected_sequences:
        raise ValueError("Chunk sequences must be contiguous and ordered")
    return b"".join(chunk.decrypt_and_decompress(key) for chunk in chunks)


def _decrypt_compressed(chunk: SnapshotChunk, key: bytes | None) -> bytes:
    aes_key = _validate_aes_key(key)
    if len(chunk.nonce) != 12 or len(chunk.auth_tag) != 16:
        raise ValueError("Invalid AES-GCM nonce or authentication tag")
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    try:
        decrypted: Any = AESGCM(aes_key).decrypt(chunk.nonce, chunk.data + chunk.auth_tag, None)
        return bytes(decrypted)
    except (InvalidTag, ValueError) as exc:
        raise ValueError("Encrypted chunk authentication failed") from exc


def _decompress(compressed: bytes, compression: CompressionAlgorithm, original_size: int) -> bytes:
    if compression == CompressionAlgorithm.ZLIB:
        try:
            data = zlib.decompress(compressed)
        except zlib.error as exc:
            raise ValueError("Compressed chunk is invalid") from exc
    elif compression == CompressionAlgorithm.NONE:
        data = compressed
    else:
        raise ValueError(f"Unsupported compression algorithm: {compression!r}")
    if len(data) != original_size:
        raise ValueError("Chunk original size mismatch")
    return data


@dataclass(frozen=True, slots=True)
class SnapshotChunk:
    """Immutable chunk of snapshot data with content-addressable storage."""

    chunk_id: str
    tenant_id: str
    snapshot_id: str
    sequence: int
    data: bytes
    content_hash: str
    compressed_size: int
    original_size: int
    compression: CompressionAlgorithm = CompressionAlgorithm.ZLIB
    encryption: EncryptionAlgorithm = EncryptionAlgorithm.AES_256_GCM
    nonce: bytes = b""
    auth_tag: bytes = b""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def create(
        cls,
        tenant_id: str,
        snapshot_id: str,
        sequence: int,
        data: bytes,
        compression: CompressionAlgorithm | str = CompressionAlgorithm.ZLIB,
        encryption: EncryptionAlgorithm | str = EncryptionAlgorithm.AES_256_GCM,
        key: bytes | None = None,
    ) -> SnapshotChunk:
        tenant_id = _validate_identifier(tenant_id, "tenant_id")
        _validate_identifier(snapshot_id, "snapshot_id")
        if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 0:
            raise ValueError("Chunk sequence must be a non-negative integer")

        normalised_compression = _coerce_enum(
            compression, CompressionAlgorithm, "compression algorithm"
        )
        normalised_encryption = _coerce_enum(
            encryption, EncryptionAlgorithm, "encryption algorithm"
        )
        payload = _as_bytes(data)
        compressed = (
            zlib.compress(payload)
            if normalised_compression == CompressionAlgorithm.ZLIB
            else payload
        )
        content_hash = hashlib.sha256(payload).hexdigest()
        chunk_id = f"{snapshot_id}-chunk-{sequence}-{content_hash[:16]}"
        nonce = b""
        auth_tag = b""
        encrypted_data = compressed

        if normalised_encryption == EncryptionAlgorithm.AES_256_GCM:
            aes_key = _validate_aes_key(key)
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            nonce = secrets.token_bytes(12)
            encrypted_with_tag = AESGCM(aes_key).encrypt(nonce, compressed, None)
            encrypted_data = encrypted_with_tag[:-16]
            auth_tag = encrypted_with_tag[-16:]

        return cls(
            chunk_id=chunk_id,
            tenant_id=tenant_id,
            snapshot_id=snapshot_id,
            sequence=sequence,
            data=encrypted_data,
            content_hash=content_hash,
            compressed_size=len(compressed),
            original_size=len(payload),
            compression=normalised_compression,
            encryption=normalised_encryption,
            nonce=nonce,
            auth_tag=auth_tag,
        )

    def decrypt_and_decompress(self, key: bytes | None = None) -> bytes:
        """Decrypt and decompress chunk data, authenticating encrypted payloads."""
        if self.encryption == EncryptionAlgorithm.AES_256_GCM:
            compressed = _decrypt_compressed(self, key)
        elif self.encryption == EncryptionAlgorithm.NONE:
            compressed = self.data
        else:
            raise ValueError(f"Unsupported encryption algorithm: {self.encryption!r}")

        data = _decompress(compressed, self.compression, self.original_size)
        if (
            self.encryption == EncryptionAlgorithm.AES_256_GCM
            and len(compressed) != self.compressed_size
        ):
            raise ValueError("Chunk compressed size mismatch")
        expected_hash = hashlib.sha256(data).hexdigest()
        if expected_hash != self.content_hash:
            raise ValueError(
                f"Content hash mismatch: expected {self.content_hash}, got {expected_hash}"
            )
        return data

    def verify_integrity(self, key: bytes | None = None) -> bool:
        """Verify a chunk, including AES-GCM authentication when encrypted."""
        try:
            if self.encryption == EncryptionAlgorithm.AES_256_GCM:
                compressed = _decrypt_compressed(self, key)
                if len(compressed) != self.compressed_size:
                    return False
                data = _decompress(compressed, self.compression, self.original_size)
            elif self.encryption == EncryptionAlgorithm.NONE:
                data = _decompress(self.data, self.compression, self.original_size)
                if self.compressed_size != len(self.data):
                    return False
            else:
                return False
            return hashlib.sha256(data).hexdigest() == self.content_hash
        except Exception:
            return False


@dataclass(frozen=True, slots=True)
class SnapshotRecord:
    """Immutable tenant-scoped snapshot record with full lineage and integrity."""

    snapshot_id: str
    tenant_id: str
    snapshot_type: SnapshotType
    parent_snapshot_id: str | None
    base_snapshot_id: str | None
    content_hash: str
    total_size: int
    chunk_count: int
    chunks: tuple[SnapshotChunk, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)
    retention_policy: RetentionPolicy = RetentionPolicy.KEEP_ALL
    retention_params: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None
    lineage_depth: int = 0
    is_verified: bool = False
    verification_hash: str = ""

    @classmethod
    def create_full(
        cls,
        tenant_id: str,
        data: bytes,
        metadata: dict[str, Any] | None = None,
        retention_policy: RetentionPolicy | str = RetentionPolicy.KEEP_ALL,
        retention_params: dict[str, Any] | None = None,
        encryption_key: bytes | None = None,
        chunk_size: int = 64 * 1024,
    ) -> SnapshotRecord:
        tenant_id = _validate_identifier(tenant_id, "tenant_id")
        if not isinstance(chunk_size, int) or isinstance(chunk_size, bool) or chunk_size < 1:
            raise ValueError("chunk_size must be a positive integer")
        payload = _as_bytes(data)
        normalised_policy, normalised_params = _normalise_retention(
            retention_policy, retention_params
        )
        created_at = datetime.now(UTC)
        raw_chunks: list[SnapshotChunk] = []
        for sequence in range(0, len(payload), chunk_size):
            raw_chunks.append(
                SnapshotChunk.create(
                    tenant_id=tenant_id,
                    snapshot_id="pending",
                    sequence=len(raw_chunks),
                    data=payload[sequence : sequence + chunk_size],
                    compression=CompressionAlgorithm.ZLIB,
                    encryption=EncryptionAlgorithm.AES_256_GCM
                    if encryption_key is not None
                    else EncryptionAlgorithm.NONE,
                    key=encryption_key,
                )
            )

        combined_hash = _chunk_chain_hash(tuple(raw_chunks))
        snapshot_id = (
            f"snap-{tenant_id}-{combined_hash[:16]}-{int(created_at.timestamp() * 1_000_000)}"
        )
        chunks = tuple(
            replace(
                chunk,
                snapshot_id=snapshot_id,
                chunk_id=f"{snapshot_id}-chunk-{chunk.sequence}-{chunk.content_hash[:16]}",
            )
            for chunk in raw_chunks
        )
        return cls(
            snapshot_id=snapshot_id,
            tenant_id=tenant_id,
            snapshot_type=SnapshotType.FULL,
            parent_snapshot_id=None,
            base_snapshot_id=None,
            content_hash=combined_hash,
            total_size=len(payload),
            chunk_count=len(chunks),
            chunks=chunks,
            metadata=dict(metadata or {}),
            retention_policy=normalised_policy,
            retention_params=normalised_params,
            created_at=created_at,
            expires_at=_retention_expires_at(normalised_policy, normalised_params, created_at),
            lineage_depth=0,
        )

    @classmethod
    def create_incremental(
        cls,
        tenant_id: str,
        data: bytes,
        base_snapshot: SnapshotRecord,
        metadata: dict[str, Any] | None = None,
        retention_policy: RetentionPolicy | str = RetentionPolicy.KEEP_ALL,
        retention_params: dict[str, Any] | None = None,
        encryption_key: bytes | None = None,
        chunk_size: int = 64 * 1024,
        base_data: bytes | None = None,
    ) -> SnapshotRecord:
        tenant_id = _validate_identifier(tenant_id, "tenant_id")
        if base_snapshot.tenant_id != tenant_id:
            raise ValueError("Base snapshot belongs to a different tenant")
        if not isinstance(chunk_size, int) or isinstance(chunk_size, bool) or chunk_size < 1:
            raise ValueError("chunk_size must be a positive integer")
        payload = _as_bytes(data)
        normalised_policy, normalised_params = _normalise_retention(
            retention_policy, retention_params
        )
        if base_data is None:
            base_data = base_snapshot.reconstruct(encryption_key)
        delta = compute_delta(base_data, payload)
        created_at = datetime.now(UTC)
        raw_chunks: list[SnapshotChunk] = []
        for sequence in range(0, len(delta), chunk_size):
            raw_chunks.append(
                SnapshotChunk.create(
                    tenant_id=tenant_id,
                    snapshot_id="pending",
                    sequence=len(raw_chunks),
                    data=delta[sequence : sequence + chunk_size],
                    compression=CompressionAlgorithm.ZLIB,
                    encryption=EncryptionAlgorithm.AES_256_GCM
                    if encryption_key is not None
                    else EncryptionAlgorithm.NONE,
                    key=encryption_key,
                )
            )

        combined_hash = _chunk_chain_hash(tuple(raw_chunks))
        snapshot_id = (
            f"snap-{tenant_id}-{combined_hash[:16]}-{int(created_at.timestamp() * 1_000_000)}"
        )
        chunks = tuple(
            replace(
                chunk,
                snapshot_id=snapshot_id,
                chunk_id=f"{snapshot_id}-chunk-{chunk.sequence}-{chunk.content_hash[:16]}",
            )
            for chunk in raw_chunks
        )
        return cls(
            snapshot_id=snapshot_id,
            tenant_id=tenant_id,
            snapshot_type=SnapshotType.INCREMENTAL,
            parent_snapshot_id=base_snapshot.snapshot_id,
            base_snapshot_id=base_snapshot.base_snapshot_id or base_snapshot.snapshot_id,
            content_hash=combined_hash,
            total_size=len(delta),
            chunk_count=len(chunks),
            chunks=chunks,
            metadata=dict(metadata or {}),
            retention_policy=normalised_policy,
            retention_params=normalised_params,
            created_at=created_at,
            expires_at=_retention_expires_at(normalised_policy, normalised_params, created_at),
            lineage_depth=base_snapshot.lineage_depth + 1,
        )

    def reconstruct(
        self,
        encryption_key: bytes | None = None,
        base_snapshot: SnapshotRecord | None = None,
    ) -> bytes:
        """Reconstruct full data from a full snapshot or an incremental with its base."""
        if self.snapshot_type == SnapshotType.FULL:
            return _decode_chunks(self.chunks, encryption_key)
        if base_snapshot is not None:
            return self.reconstruct_with_base(base_snapshot, encryption_key)
        raise ValueError("Incremental snapshots require a base snapshot for reconstruction")

    def reconstruct_with_base(
        self, base_snapshot: SnapshotRecord, encryption_key: bytes | None = None
    ) -> bytes:
        """Reconstruct an incremental snapshot using its immediate parent."""
        if self.snapshot_type != SnapshotType.INCREMENTAL:
            return self.reconstruct(encryption_key)
        if base_snapshot.tenant_id != self.tenant_id:
            raise ValueError("Base snapshot belongs to a different tenant")
        if base_snapshot.snapshot_id != self.parent_snapshot_id:
            raise ValueError("The supplied base is not the immediate parent snapshot")
        base_data = base_snapshot.reconstruct(encryption_key)
        delta = _decode_chunks(self.chunks, encryption_key)
        return apply_delta(base_data, delta)

    def verify_integrity(
        self,
        encryption_key: bytes | None = None,
        base_snapshot: SnapshotRecord | None = None,
        base_data: bytes | None = None,
    ) -> tuple[bool, str]:
        """Verify record metadata, chunk integrity, and an optional data hash."""
        if self.chunk_count != len(self.chunks):
            return False, "Snapshot chunk count mismatch"
        if [chunk.sequence for chunk in self.chunks] != list(range(self.chunk_count)):
            return False, "Snapshot chunk sequences are invalid"
        if any(
            chunk.tenant_id != self.tenant_id or chunk.snapshot_id != self.snapshot_id
            for chunk in self.chunks
        ):
            return False, "Snapshot chunk scope mismatch"
        if self.snapshot_type not in SnapshotType:
            return False, f"Unsupported snapshot type: {self.snapshot_type!r}"
        if self.retention_policy not in RetentionPolicy:
            return False, f"Unsupported retention policy: {self.retention_policy!r}"
        if (
            not isinstance(self.total_size, int)
            or isinstance(self.total_size, bool)
            or self.total_size < 0
        ):
            return False, "Snapshot total size is invalid"
        if not isinstance(self.lineage_depth, int) or self.lineage_depth < 0:
            return False, "Snapshot lineage depth is invalid"

        computed_hash = _chunk_chain_hash(self.chunks)
        if computed_hash != self.content_hash:
            return (
                False,
                f"Snapshot content hash mismatch: expected {self.content_hash}, "
                f"got {computed_hash}",
            )

        for chunk in self.chunks:
            if not chunk.verify_integrity(encryption_key):
                return False, f"Chunk {chunk.chunk_id} integrity check failed"

        if self.is_verified and not self.verification_hash:
            return False, "Verified snapshot has no verification hash"

        try:
            if self.snapshot_type == SnapshotType.FULL:
                reconstructed = self.reconstruct(encryption_key)
                if len(reconstructed) != self.total_size:
                    return False, "Snapshot total size mismatch"
            else:
                delta = _decode_chunks(self.chunks, encryption_key)
                if len(delta) != self.total_size:
                    return False, "Incremental delta size mismatch"
                if base_data is not None:
                    reconstructed = apply_delta(base_data, delta)
                elif base_snapshot is not None:
                    reconstructed = self.reconstruct_with_base(base_snapshot, encryption_key)
                else:
                    reconstructed = delta

            if self.verification_hash:
                verification = hashlib.sha256(reconstructed).hexdigest()
                if verification != self.verification_hash:
                    return (
                        False,
                        f"Data verification hash mismatch: expected {self.verification_hash}, "
                        f"got {verification}",
                    )
        except Exception as exc:
            return False, f"Snapshot reconstruction failed: {exc}"

        return True, "OK"

    def mark_verified(
        self,
        encryption_key: bytes | None = None,
        base_snapshot: SnapshotRecord | None = None,
        base_data: bytes | None = None,
    ) -> SnapshotRecord:
        """Create a new record with a hash of the materialized snapshot data."""
        if self.snapshot_type == SnapshotType.FULL:
            reconstructed = self.reconstruct(encryption_key)
        elif base_data is not None:
            reconstructed = apply_delta(base_data, _decode_chunks(self.chunks, encryption_key))
        elif base_snapshot is not None:
            reconstructed = self.reconstruct_with_base(base_snapshot, encryption_key)
        else:
            reconstructed = _decode_chunks(self.chunks, encryption_key)
        verification_hash = hashlib.sha256(reconstructed).hexdigest()
        return SnapshotRecord(
            snapshot_id=self.snapshot_id,
            tenant_id=self.tenant_id,
            snapshot_type=self.snapshot_type,
            parent_snapshot_id=self.parent_snapshot_id,
            base_snapshot_id=self.base_snapshot_id,
            content_hash=self.content_hash,
            total_size=self.total_size,
            chunk_count=self.chunk_count,
            chunks=self.chunks,
            metadata=self.metadata,
            retention_policy=self.retention_policy,
            retention_params=self.retention_params,
            created_at=self.created_at,
            expires_at=self.expires_at,
            lineage_depth=self.lineage_depth,
            is_verified=True,
            verification_hash=verification_hash,
        )

    def is_expired(self, now: datetime | None = None) -> bool:
        """Check whether the snapshot's time-based retention window has elapsed."""
        if self.expires_at is None:
            return False
        check_time = now or datetime.now(UTC)
        if check_time.tzinfo is None:
            check_time = check_time.replace(tzinfo=UTC)
        expires_at = self.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        return check_time >= expires_at

    def get_lineage(self) -> list[str]:
        """Return only lineage IDs backed by actual records."""
        return [self.snapshot_id]


def compute_delta(old_data: bytes, new_data: bytes) -> bytes:
    """Compute a binary-safe delta with explicit lengths and a versioned envelope."""
    old = _as_bytes(old_data, "old_data")
    new = _as_bytes(new_data, "new_data")
    prefix = 0
    shared_prefix = min(len(old), len(new))
    while prefix < shared_prefix and old[prefix] == new[prefix]:
        prefix += 1

    suffix = 0
    shared_suffix = min(len(old) - prefix, len(new) - prefix)
    while suffix < shared_suffix and old[len(old) - suffix - 1] == new[len(new) - suffix - 1]:
        suffix += 1

    old_middle_end = len(old) - suffix if suffix else len(old)
    new_middle_end = len(new) - suffix if suffix else len(new)
    old_middle = old[prefix:old_middle_end]
    new_middle = new[prefix:new_middle_end]
    suffix_data = old[len(old) - suffix :] if suffix else b""
    header = struct.pack(">QQQQQ", prefix, len(old_middle), len(new_middle), len(old), len(new))
    return _DELTA_MAGIC + header + old[:prefix] + old_middle + new_middle + suffix_data


def apply_delta(base_data: bytes, delta: bytes) -> bytes:
    """Apply a delta produced by :func:`compute_delta`."""
    encoded_delta = _as_bytes(delta, "delta")
    if not encoded_delta.startswith(_DELTA_MAGIC):
        raise ValueError("Unsupported or corrupted delta format")
    offset = len(_DELTA_MAGIC)
    header_size = struct.calcsize(">QQQQQ")
    if len(encoded_delta) < offset + header_size:
        raise ValueError("Corrupted delta header")
    prefix_len, old_middle_len, new_middle_len, old_size, new_size = struct.unpack_from(
        ">QQQQQ", encoded_delta, offset
    )
    offset += header_size
    required = prefix_len + old_middle_len + new_middle_len
    if len(encoded_delta) < offset + required:
        raise ValueError("Corrupted delta body")
    prefix = encoded_delta[offset : offset + prefix_len]
    offset += prefix_len
    old_middle = encoded_delta[offset : offset + old_middle_len]
    offset += old_middle_len
    new_middle = encoded_delta[offset : offset + new_middle_len]
    offset += new_middle_len
    suffix = encoded_delta[offset:]
    if len(suffix) != (new_size - prefix_len - new_middle_len):
        raise ValueError("Corrupted delta suffix")
    if len(base_data) != old_size:
        raise ValueError("Delta base data size mismatch")
    if old_middle != base_data[prefix_len : prefix_len + old_middle_len]:
        raise ValueError("Delta base data mismatch")
    reconstructed = prefix + new_middle + suffix
    if len(reconstructed) != new_size:
        raise ValueError("Corrupted delta output size")
    return reconstructed
