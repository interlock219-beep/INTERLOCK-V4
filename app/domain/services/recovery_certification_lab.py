"""Recovery adapter certification lab (Interlock V5).

Certifies recovery adapters in two tiers:

1. **Contract battery** — every adapter must satisfy the V5 adapter contract
   (:func:`RecoveryAdapterRegistry.validate_contract`): identity, the full
   async protocol surface, legacy trio, and a known capability value.
2. **Behavioral probes** — adapters whose targets are self-contained (process
   environment, temporary directories, temporary hosts/config files) run real
   capture -> drift -> simulate -> compensate -> verify round-trips plus
   adversarial probes (injection, payload redirection, tampered snapshots,
   idempotency, tenant isolation) inside an isolated temporary working
   directory.
3. **Contract-only** — adapters that require live external systems (databases,
   cloud providers, message queues, ...) are certified for contract
   conformance only and reported as awaiting external validation.

Results are consumed by ``INTERLOCK_V5_ADAPTER_CAPABILITY_MATRIX.md``.
Honesty rule: this lab never fakes a behavioral result for an adapter it
cannot exercise locally — such adapters are reported as contract-only.
"""

from __future__ import annotations

import tempfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.domain.services.recovery_adapter_registry import RecoveryAdapterRegistry

BehavioralProbe = Callable[[Path], Awaitable[list["ProbeResult"]]]


@dataclass(frozen=True)
class ProbeResult:
    """Outcome of one certification probe."""

    probe: str
    passed: bool
    details: dict[str, Any] = field(default_factory=dict)


def probe(name: str, passed: bool, **details: Any) -> ProbeResult:
    return ProbeResult(probe=name, passed=bool(passed), details=details)


async def run_probe_check(
    name: str, fn: Callable[[], Awaitable[ProbeResult]]
) -> ProbeResult:
    """Run one probe check, converting any exception into a failed result."""
    try:
        return await fn()
    except Exception as exc:  # noqa: BLE001 - probe failures are reported, not raised
        return ProbeResult(
            probe=name,
            passed=False,
            details={"error": f"{type(exc).__name__}: {exc}"},
        )


@dataclass(frozen=True)
class AdapterCertification:
    """Certification outcome for a single adapter."""

    adapter_name: str
    adapter_type: str
    mode: str  # "behavioral" | "contract_only"
    contract_problems: tuple[str, ...]
    probes: tuple[ProbeResult, ...]

    @property
    def contract_ok(self) -> bool:
        return not self.contract_problems

    @property
    def certified(self) -> bool:
        if not self.contract_ok:
            return False
        if self.mode == "contract_only":
            return True
        return all(p.passed for p in self.probes)

    @property
    def scope(self) -> str:
        if not self.certified:
            return "not_certified"
        if self.mode == "contract_only":
            return "contract_only__external_validation_required"
        return "contract_plus_behavioral__tested_local_scope"

    @property
    def failed_probes(self) -> tuple[str, ...]:
        return tuple(p.probe for p in self.probes if not p.passed)


@dataclass(frozen=True)
class CertificationReport:
    """Full certification run report."""

    generated_at: str
    results: tuple[AdapterCertification, ...]

    @property
    def all_certified(self) -> bool:
        return bool(self.results) and all(r.certified for r in self.results)

    def get(self, adapter_name: str) -> AdapterCertification | None:
        for result in self.results:
            if result.adapter_name == adapter_name:
                return result
        return None

    @property
    def failed(self) -> tuple[AdapterCertification, ...]:
        return tuple(r for r in self.results if not r.certified)

    def summary(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "total": len(self.results),
            "certified": sum(1 for r in self.results if r.certified),
            "behavioral": sum(1 for r in self.results if r.mode == "behavioral"),
            "contract_only": sum(1 for r in self.results if r.mode == "contract_only"),
            "failed": len(self.failed),
            "failed_adapters": [r.adapter_name for r in self.failed],
            "scopes": {r.adapter_name: r.scope for r in self.results},
        }


class RecoveryCertificationLab:
    """Runs the certification battery against a set of adapters.

    Behavioral probes are keyed by ``adapter_name``; an adapter with no
    registered probe is certified contract-only (honest reporting — no
    fabricated behavioral results).
    """

    def __init__(
        self,
        adapters: list[Any] | None = None,
        *,
        behavioral_probes: dict[str, BehavioralProbe] | None = None,
    ) -> None:
        self._adapters: list[Any] = list(adapters or [])
        self._probes: dict[str, BehavioralProbe] = dict(behavioral_probes or {})

    def add_adapter(self, adapter: Any) -> RecoveryCertificationLab:
        self._adapters.append(adapter)
        return self

    def register_probe(self, adapter_name: str, probe_fn: BehavioralProbe) -> None:
        self._probes[adapter_name] = probe_fn

    async def certify(self, adapter: Any) -> AdapterCertification:
        validation = RecoveryAdapterRegistry.validate_contract(adapter)
        adapter_name = validation.adapter_name
        probe_fn = self._probes.get(adapter_name)
        mode = "behavioral" if probe_fn is not None else "contract_only"

        results: tuple[ProbeResult, ...] = ()
        if probe_fn is not None:
            with tempfile.TemporaryDirectory(
                prefix=f"interlock-cert-{adapter_name}-"
            ) as tmp:
                try:
                    results = tuple(await probe_fn(Path(tmp)))
                except Exception as exc:  # noqa: BLE001 - report, never claim
                    results = (
                        ProbeResult(
                            probe="probe_infrastructure",
                            passed=False,
                            details={"error": f"{type(exc).__name__}: {exc}"},
                        ),
                    )

        return AdapterCertification(
            adapter_name=adapter_name,
            adapter_type=str(getattr(adapter, "adapter_type", "")),
            mode=mode,
            contract_problems=validation.problems,
            probes=results,
        )

    async def certify_all(self) -> CertificationReport:
        results = tuple([await self.certify(a) for a in self._adapters])
        return CertificationReport(
            generated_at=datetime.now(UTC).isoformat(), results=results
        )
