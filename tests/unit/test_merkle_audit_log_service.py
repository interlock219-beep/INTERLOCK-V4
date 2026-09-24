from __future__ import annotations

import pytest
import pytest_asyncio

from app.domain.entities.forensic_types import (
    AuditEventSeverity,
    AuditEventType,
    AuditLogEntry,
    MerkleProof,
    IntegrityProof,
)
from app.domain.services.merkle_audit_log_service import MerkleAuditLogService
from app.infrastructure.persistence.repositories.in_memory_forensic_audit_repository import (
    InMemoryForensicAuditRepository,
)


@pytest.fixture
def repo():
    return InMemoryForensicAuditRepository()


@pytest.fixture
def service(repo):
    return MerkleAuditLogService(audit_repository=repo)


def _make_entry(
    tenant_id: str = "tenant-1",
    entry_id: str = "entry-1",
    description: str = "test event",
) -> AuditLogEntry:
    return AuditLogEntry(
        entry_id=entry_id,
        tenant_id=tenant_id,
        event_type=AuditEventType.ACTION_EXECUTED,
        severity=AuditEventSeverity.INFO,
        description=description,
    )


@pytest.mark.asyncio
async def test_append_entry_updates_merkle_root(service, repo, tenant_id="tenant-1"):
    entry = _make_entry(tenant_id)
    saved = await service.append_entry(tenant_id, entry)

    assert saved.entry_id == "entry-1"

    root = await service.get_root(tenant_id)
    assert root is not None
    root_hash, tree_size = root
    assert tree_size == 1
    assert len(root_hash) == 64


@pytest.mark.asyncio
async def test_compute_merkle_root_single_leaf(service):
    entry = _make_entry()
    leaf_hash = service.compute_leaf_hash(entry)
    root = service.compute_merkle_root([leaf_hash])
    assert len(root) == 64


@pytest.mark.asyncio
async def test_compute_merkle_root_empty_tree(service):
    root = service.compute_merkle_root([])
    assert len(root) == 64


@pytest.mark.asyncio
async def test_generate_and_verify_inclusion_proof(service, repo, tenant_id="tenant-1"):
    entry1 = _make_entry(tenant_id, "entry-1", "first")
    entry2 = _make_entry(tenant_id, "entry-2", "second")
    entry3 = _make_entry(tenant_id, "entry-3", "third")

    await service.append_entry(tenant_id, entry1)
    await service.append_entry(tenant_id, entry2)
    await service.append_entry(tenant_id, entry3)

    root = await service.get_root(tenant_id)
    assert root is not None
    root_hash, tree_size = root
    assert tree_size == 3

    leaf_hashes = service._leaf_hashes[tenant_id]
    leaf_hash_entry2 = leaf_hashes[1]

    proof = service.generate_inclusion_proof(tenant_id, leaf_hash_entry2, leaf_hashes)
    assert proof is not None
    assert proof.entry_id == leaf_hash_entry2
    assert len(proof.path) > 0
    assert len(proof.path) == len(proof.path_directions)
    assert proof.verify() is True


@pytest.mark.asyncio
async def test_inclusion_proof_fails_with_wrong_root(service, repo, tenant_id="tenant-1"):
    entry = _make_entry(tenant_id)
    await service.append_entry(tenant_id, entry)

    root = await service.get_root(tenant_id)
    assert root is not None
    leaf_hashes = service._leaf_hashes[tenant_id]

    from app.domain.entities.forensic_types import MerkleProof

    proof = MerkleProof(
        entry_id=leaf_hashes[0],
        tenant_id=tenant_id,
        leaf_hash=leaf_hashes[0],
        root_hash="0" * 64,
        tree_size=1,
        node_index=0,
        path=[],
        path_directions=[],
    )
    assert proof.verify() is False


@pytest.mark.asyncio
async def test_append_duplicate_entry_raises(service, repo, tenant_id="tenant-1"):
    entry = _make_entry(tenant_id, "dup-1")
    await service.append_entry(tenant_id, entry)

    with pytest.raises(Exception, match="already exists"):
        await service.append_entry(tenant_id, entry)


@pytest.mark.asyncio
async def test_append_multiple_entries_grows_tree(service, repo, tenant_id="tenant-1"):
    for i in range(5):
        await service.append_entry(tenant_id, _make_entry(tenant_id, f"entry-{i}"))

    root = await service.get_root(tenant_id)
    assert root is not None
    assert root[1] == 5
    assert len(service._leaf_hashes[tenant_id]) == 5


@pytest.mark.asyncio
async def test_build_integrity_proof(service, repo, tenant_id="tenant-1"):
    entry1 = _make_entry(tenant_id, "entry-1")
    entry2 = _make_entry(tenant_id, "entry-2")
    await service.append_entry(tenant_id, entry1)
    await service.append_entry(tenant_id, entry2)

    leaf_hashes = service._leaf_hashes[tenant_id]
    proof = service.build_integrity_proof(
        tenant_id,
        [leaf_hashes[0], leaf_hashes[1]],
        leaf_hashes,
    )

    assert proof.is_valid is True
    assert proof.chain_length == 2
    assert len(proof.issues) == 0


@pytest.mark.asyncio
async def test_create_chain_link(service, tenant_id="tenant-1"):
    link = service.create_chain_link(
        tenant_id,
        "evidence-parent",
        "evidence-child",
        "hash-parent",
        "hash-child",
    )

    assert link.parent_evidence_id == "evidence-parent"
    assert link.child_evidence_id == "evidence-child"
    assert len(link.link_hash) == 64
    assert link.chain_entry_hash != ""  # property computes a hash including created_at


@pytest.mark.asyncio
async def test_get_audit_trail(service, repo, tenant_id="tenant-1"):
    await service.append_entry(tenant_id, _make_entry(tenant_id, "entry-1"))
    await service.append_entry(tenant_id, _make_entry(tenant_id, "entry-2"))

    trail = await service.get_audit_trail(tenant_id, ["entry-1", "entry-2"])
    assert len(trail) == 2
    assert trail[0]["entry_id"] == "entry-1"
    assert trail[1]["entry_id"] == "entry-2"


@pytest.mark.asyncio
async def test_get_audit_trail_skips_missing(service, repo, tenant_id="tenant-1"):
    await service.append_entry(tenant_id, _make_entry(tenant_id, "entry-1"))

    trail = await service.get_audit_trail(tenant_id, ["entry-1", "missing-entry"])
    assert len(trail) == 1
    assert trail[0]["entry_id"] == "entry-1"


@pytest.mark.asyncio
async def test_root_persisted_in_repository(service, repo, tenant_id="tenant-1"):
    await service.append_entry(tenant_id, _make_entry(tenant_id))

    root_from_repo = await repo.get_latest_merkle_root(tenant_id)
    assert root_from_repo is not None
    root_from_service = await service.get_root(tenant_id)
    assert root_from_service == root_from_repo


@pytest.mark.asyncio
async def test_tenant_isolation(service, repo):
    await service.append_entry("tenant-a", _make_entry("tenant-a", "entry-a1"))
    await service.append_entry("tenant-b", _make_entry("tenant-b", "entry-b1"))

    root_a = await service.get_root("tenant-a")
    root_b = await service.get_root("tenant-b")
    assert root_a is not None
    assert root_b is not None
    assert root_a[0] != root_b[0]
    assert root_a[1] == 1
    assert root_b[1] == 1
