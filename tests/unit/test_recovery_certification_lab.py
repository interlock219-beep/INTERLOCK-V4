"""Interlock V5 — recovery adapter certification lab tests.

Covers the two-tier certification model (contract battery + behavioral
probes), honest contract-only reporting, failure propagation for broken
contracts / failing / crashing probes, and the full standard probe suite.
"""

from __future__ import annotations

from pathlib import Path

from app.domain.services.recovery_certification_lab import (
    ProbeResult,
    RecoveryCertificationLab,
    probe,
    run_probe_check,
)
from app.infrastructure.recovery.archive_recovery_adapter import ArchiveRecoveryAdapter
from app.infrastructure.recovery.certification_probes import standard_behavioral_probes
from app.infrastructure.recovery.config_recovery_adapter import ConfigRecoveryAdapter
from app.infrastructure.recovery.environment_recovery_adapter import (
    EnvironmentRecoveryAdapter,
)
from app.infrastructure.recovery.filesystem_recovery_adapter import (
    FilesystemRecoveryAdapter,
)
from app.infrastructure.recovery.hosts_recovery_adapter import HostsRecoveryAdapter
from app.infrastructure.recovery.mock_adapter import MockRecoveryAdapter


def _behavioral_adapters(tmp_path: Path) -> list:
    return [
        EnvironmentRecoveryAdapter(environ={}),
        ArchiveRecoveryAdapter(state_dir=tmp_path / "arc-state"),
        HostsRecoveryAdapter(hosts_path=tmp_path / "hosts"),
        ConfigRecoveryAdapter(config_dir=tmp_path / "cfg"),
        FilesystemRecoveryAdapter(base_path=tmp_path / "fs"),
    ]


async def test_behavioral_adapters_certify_with_passing_probes(tmp_path: Path):
    lab = RecoveryCertificationLab(
        _behavioral_adapters(tmp_path),
        behavioral_probes=standard_behavioral_probes(),
    )
    report = await lab.certify_all()

    assert len(report.results) == 5
    for result in report.results:
        assert result.mode == "behavioral"
        assert result.contract_ok, (result.adapter_name, result.contract_problems)
        assert result.probes, result.adapter_name
        assert result.failed_probes == (), (
            result.adapter_name,
            result.failed_probes,
        )
        assert result.certified is True
        assert result.scope == "contract_plus_behavioral__tested_local_scope"

    assert report.all_certified is True
    assert report.failed == ()
    summary = report.summary()
    assert summary["total"] == 5
    assert summary["certified"] == 5
    assert summary["behavioral"] == 5
    assert summary["contract_only"] == 0
    assert summary["failed"] == 0


async def test_contract_only_adapter_reported_honestly(tmp_path: Path):
    lab = RecoveryCertificationLab(
        [MockRecoveryAdapter(scenario="success")],
        behavioral_probes=standard_behavioral_probes(),
    )
    report = await lab.certify_all()

    result = report.get("mock")
    assert result is not None
    assert result.mode == "contract_only"
    assert result.probes == ()  # no fabricated behavioral evidence
    assert result.certified is True
    assert result.scope == "contract_only__external_validation_required"


async def test_broken_contract_fails_certification():
    class BrokenAdapter:
        adapter_name = "broken"
        adapter_type = "broken"
        capability = "mock"
        # No protocol methods at all.

    lab = RecoveryCertificationLab([BrokenAdapter()])
    report = await lab.certify_all()

    result = report.get("broken")
    assert result is not None
    assert result.contract_ok is False
    assert any("protocol method" in p for p in result.contract_problems)
    assert result.certified is False
    assert result.scope == "not_certified"
    assert report.all_certified is False
    assert [r.adapter_name for r in report.failed] == ["broken"]


async def test_failing_probe_fails_certification(tmp_path: Path):
    async def bad_probe(_workdir: Path) -> list[ProbeResult]:
        return [probe("round_trip", True), probe("adversarial_check", False, why="x")]

    lab = RecoveryCertificationLab(
        [EnvironmentRecoveryAdapter(environ={})],
        behavioral_probes={"environment_recovery": bad_probe},
    )
    report = await lab.certify_all()

    result = report.get("environment_recovery")
    assert result is not None
    assert result.certified is False
    assert result.failed_probes == ("adversarial_check",)
    assert result.scope == "not_certified"


async def test_crashing_probe_is_reported_as_failure():
    async def exploding_probe(_workdir: Path) -> list[ProbeResult]:
        raise RuntimeError("probe infrastructure broke")

    lab = RecoveryCertificationLab(
        [EnvironmentRecoveryAdapter(environ={})],
        behavioral_probes={"environment_recovery": exploding_probe},
    )
    report = await lab.certify_all()

    result = report.get("environment_recovery")
    assert result is not None
    assert result.certified is False  # crash -> report failed, never claimed


async def test_run_probe_check_converts_exception_to_failed_result():
    async def boom() -> ProbeResult:
        raise ValueError("inner failure")

    result = await run_probe_check("check", boom)
    assert result.passed is False
    assert result.probe == "check"
    assert "ValueError" in result.details["error"]


async def test_standard_probe_suite_passes_end_to_end(tmp_path: Path):
    """Every registered behavioral probe passes against its isolated workspace."""
    failures: list[str] = []
    for adapter_name, probe_fn in standard_behavioral_probes().items():
        workdir = tmp_path / adapter_name
        workdir.mkdir()
        results = await probe_fn(workdir)
        assert results, f"{adapter_name}: probe returned no results"
        for result in results:
            if not result.passed:
                failures.append(f"{adapter_name}:{result.probe} -> {result.details}")

    assert failures == [], "\n".join(failures)


async def test_certify_is_idempotent_and_reports_timestamp():
    lab = RecoveryCertificationLab([MockRecoveryAdapter(scenario="success")])
    first = await lab.certify_all()
    second = await lab.certify_all()

    assert first.generated_at and second.generated_at
    assert [r.adapter_name for r in first.results] == [
        r.adapter_name for r in second.results
    ]
    assert first.all_certified and second.all_certified
