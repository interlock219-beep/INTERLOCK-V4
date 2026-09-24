from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.domain.entities.snapshot_types import (
    CompressionAlgorithm,
    EncryptionAlgorithm,
    RetentionPolicy,
    SnapshotChunk,
    apply_delta,
    compute_delta,
)
from app.domain.repositories.snapshot_repository import (
    FilesystemSnapshotRepository,
    InMemorySnapshotRepository,
)
from app.domain.services.snapshot_intelligence import SnapshotIntelligenceService

KEY = b"k" * 32


@pytest.mark.asyncio
async def test_capture_text_and_binary_round_trip():
    service = SnapshotIntelligenceService(InMemorySnapshotRepository())

    text_snapshot = await service.capture("tenant-text", "hello snapshot")
    binary_snapshot = await service.capture("tenant-binary", b"\x00\x01\xffbinary\x00data")

    assert await service.reconstruct("tenant-text", text_snapshot.snapshot_id) == b"hello snapshot"
    assert (
        await service.reconstruct("tenant-binary", binary_snapshot.snapshot_id)
        == b"\x00\x01\xffbinary\x00data"
    )


@pytest.mark.asyncio
async def test_incremental_reconstruction_supports_base_chains():
    service = SnapshotIntelligenceService(InMemorySnapshotRepository(), chunk_size=4)
    full = await service.capture("tenant-chain", b"full-base-data")
    first = await service.capture_incremental(
        "tenant-chain", b"full-base-changed", full.snapshot_id
    )
    second = await service.capture_incremental(
        "tenant-chain", b"final-chain-data", first.snapshot_id
    )

    assert (
        await service.reconstruct_from_chain("tenant-chain", second.snapshot_id)
        == b"final-chain-data"
    )
    lineage = await service.get_lineage("tenant-chain", second.snapshot_id)
    assert [snapshot.snapshot_id for snapshot in lineage] == [
        full.snapshot_id,
        first.snapshot_id,
        second.snapshot_id,
    ]


def test_binary_delta_is_safe_for_nulls_and_header_like_bytes():
    cases = [
        (b"", b"\x00\x01\x02"),
        (b"\x00\x01\x02", b""),
        (b"---\x00+++not-a-header", b"+++\x00---changed"),
        (b"same-suffix-and-prefix", b"same-suffix-and-prefix"),
        (bytes(range(256)) * 3, b"prefix" + bytes(range(255, -1, -1)) + b"suffix"),
    ]

    for old_data, new_data in cases:
        assert apply_delta(old_data, compute_delta(old_data, new_data)) == new_data


@pytest.mark.asyncio
async def test_compression_encryption_and_filesystem_enum_round_trip(tmp_path: Path):
    chunk = SnapshotChunk.create(
        tenant_id="tenant-crypto",
        snapshot_id="snapshot-crypto",
        sequence=0,
        data=b"\x00" * 128 + b"compressible",
        compression=CompressionAlgorithm.ZLIB,
        encryption=EncryptionAlgorithm.AES_256_GCM,
        key=KEY,
    )

    assert chunk.compression == CompressionAlgorithm.ZLIB
    assert chunk.encryption == EncryptionAlgorithm.AES_256_GCM
    assert chunk.verify_integrity(KEY)
    assert not chunk.verify_integrity()

    repository = FilesystemSnapshotRepository(tmp_path / "snapshots")
    service = SnapshotIntelligenceService(repository, default_encryption_key=KEY)
    snapshot = await service.capture(
        "tenant-crypto",
        b"filesystem encrypted payload",
        retention_policy=RetentionPolicy.KEEP_WITHIN_DAYS,
        retention_params={"days": 7},
    )

    loaded = await repository.get("tenant-crypto", snapshot.snapshot_id)
    assert loaded is not None
    assert loaded.chunks[0].compression == CompressionAlgorithm.ZLIB
    assert loaded.retention_policy == RetentionPolicy.KEEP_WITHIN_DAYS
    assert (
        await service.reconstruct("tenant-crypto", snapshot.snapshot_id)
        == b"filesystem encrypted payload"
    )


def test_encrypted_chunk_tampering_is_rejected():
    chunk = SnapshotChunk.create(
        tenant_id="tenant-tamper",
        snapshot_id="snapshot-tamper",
        sequence=0,
        data=b"authenticated payload",
        encryption=EncryptionAlgorithm.AES_256_GCM,
        key=KEY,
    )
    tampered = replace(chunk, data=bytes([chunk.data[0] ^ 1]) + chunk.data[1:])

    assert chunk.verify_integrity(KEY)
    assert not tampered.verify_integrity(KEY)
    with pytest.raises(ValueError, match="32-byte"):
        SnapshotChunk.create(
            tenant_id="tenant-tamper",
            snapshot_id="snapshot-tamper",
            sequence=0,
            data=b"payload",
            encryption=EncryptionAlgorithm.AES_256_GCM,
            key=b"short",
        )


@pytest.mark.asyncio
async def test_snapshot_tampering_is_detected_by_service():
    repository = InMemorySnapshotRepository()
    service = SnapshotIntelligenceService(repository, default_encryption_key=KEY)
    snapshot = await service.capture("tenant-tamper-service", b"original payload")
    tampered = replace(
        snapshot, chunks=(replace(snapshot.chunks[0], data=b"X" + snapshot.chunks[0].data[1:]),)
    )
    await repository.save(tampered)

    assert (await service.verify("tenant-tamper-service", snapshot.snapshot_id))[0] is False
    with pytest.raises(ValueError, match="integrity"):
        await service.reconstruct("tenant-tamper-service", snapshot.snapshot_id)


@pytest.mark.asyncio
async def test_lineage_contains_only_real_records():
    repository = InMemorySnapshotRepository()
    service = SnapshotIntelligenceService(repository)
    full = await service.capture("tenant-lineage", b"base")
    incremental = await service.capture_incremental("tenant-lineage", b"changed", full.snapshot_id)

    assert full.get_lineage() == [full.snapshot_id]
    lineage = await repository.get_lineage("tenant-lineage", incremental.snapshot_id)
    assert [record.snapshot_id for record in lineage] == [full.snapshot_id, incremental.snapshot_id]
    assert all(record.content_hash for record in lineage)


@pytest.mark.asyncio
async def test_retention_policies_delete_expired_and_excess_snapshots():
    repository = InMemorySnapshotRepository()
    service = SnapshotIntelligenceService(repository, chunk_size=4)

    for value in (b"one", b"two", b"three"):
        await service.capture(
            "tenant-retention-count",
            value,
            retention_policy=RetentionPolicy.KEEP_LAST_N,
            retention_params={"count": 2},
        )
    assert len(await service.list_snapshots("tenant-retention-count")) == 3
    assert await service.delete_expired("tenant-retention-count") == 1
    assert len(await service.list_snapshots("tenant-retention-count")) == 2

    expired_repository = InMemorySnapshotRepository()
    expired_service = SnapshotIntelligenceService(expired_repository)
    await expired_service.capture(
        "tenant-retention-time",
        b"expire",
        retention_policy=RetentionPolicy.KEEP_WITHIN_DAYS,
        retention_params={"days": 0},
    )
    assert await expired_service.delete_expired("tenant-retention-time", datetime.now(UTC)) == 1
    assert await expired_service.list_snapshots("tenant-retention-time") == []


@pytest.mark.asyncio
async def test_tenant_and_path_isolation(tmp_path: Path):
    repository = InMemorySnapshotRepository()
    service = SnapshotIntelligenceService(repository)
    snapshot = await service.capture("../tenant-a", b"tenant A")

    assert await service.get("tenant-b", snapshot.snapshot_id) is None
    assert await service.reconstruct("../tenant-a", snapshot.snapshot_id) == b"tenant A"

    filesystem = FilesystemSnapshotRepository(tmp_path / "filesystem")
    tenant_path = filesystem._tenant_path("../tenant-a")
    snapshot_path = filesystem._snapshot_path("../tenant-a", "../snapshot-id")
    base = (tmp_path / "filesystem").resolve()
    assert tenant_path.is_relative_to(base)
    assert snapshot_path.is_relative_to(base)
    assert not (tmp_path / "snapshot-id.json").exists()


@pytest.mark.asyncio
async def test_readiness_is_false_for_unverified_or_corrupt_snapshots():
    repository = InMemorySnapshotRepository()
    service = SnapshotIntelligenceService(repository, default_encryption_key=KEY)
    unverified = await service.capture("tenant-readiness", b"unverified", verify=False)

    readiness = await service.readiness("tenant-readiness")
    assert readiness.ready is False
    assert readiness.unverified_snapshots == 1

    tampered = replace(unverified, is_verified=True, verification_hash="0" * 64)
    await repository.save(tampered)
    readiness = await service.readiness("tenant-readiness")
    assert readiness.ready is False
    assert readiness.storage_healthy is False


@pytest.mark.asyncio
async def test_deduplication_reports_repeated_content_hashes():
    repository = InMemorySnapshotRepository()
    service = SnapshotIntelligenceService(repository, chunk_size=2)
    snapshot = await service.capture("tenant-dedup", b"AAAAAAAA")

    assert await service.deduplicate_chunks("tenant-dedup", snapshot.snapshot_id) >= 1
