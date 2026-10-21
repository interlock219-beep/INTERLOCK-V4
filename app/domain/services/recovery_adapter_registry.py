"""Interlock V5 recovery adapter capability registry.

Central, fail-closed registry for every recovery adapter the platform is
allowed to use.  The registry is the single authority for:

- **Contract validation** – an adapter that does not implement the full
  :class:`~app.domain.services.recovery_adapter.CompensatingActionAdapter`
  protocol surface is rejected at registration time, before any planner can
  select it.
- **Capability declarations** – each registration captures the adapter's
  :class:`~app.domain.entities.causal_state_types.AdapterCapabilityDeclaration`
  so planning, certification, and reporting all read the same source of
  truth.
- **Selection metadata** – resource-kind prefixes document which resource
  families (``file:``, ``db:``, ``env:``, ``archive:``, ``dns:``, …) an
  adapter is responsible for.
- **Auditable enumeration** – ``capability_matrix()`` produces the row set
  used by the V5 adapter capability matrix and certification lab.

The registry never instantiates adapters itself; callers register concrete
instances, which keeps environment-specific wiring (workspace paths, DSNs,
feature flags) outside the domain layer.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any

from app.domain.entities.causal_state_types import AdapterCapabilityDeclaration
from app.domain.entities.surgical_recovery_types import AdapterCapability
from app.domain.services.recovery_adapter import RecoveryAdapter


class AdapterContractError(Exception):
    """Raised when an adapter violates the V5 adapter contract."""


#: Protocol methods every registered adapter must expose (all coroutines).
REQUIRED_PROTOCOL_METHODS: tuple[str, ...] = (
    "supports",
    "capture_recovery_evidence",
    "classify_reversibility",
    "simulate",
    "check_preconditions",
    "detect_drift",
    "generate_compensation",
    "execute_compensation",
    "verify",
    "check_conflicts",
    "declare_capabilities",
)

#: Legacy methods required only for adapters extending :class:`RecoveryAdapter`.
REQUIRED_LEGACY_METHODS: tuple[str, ...] = (
    "can_recover",
    "preview_recovery",
    "execute_recovery",
)


@dataclass(frozen=True)
class AdapterRegistration:
    """Immutable record of a registered adapter."""

    adapter: Any
    adapter_name: str
    adapter_type: str
    capability: str
    resource_kinds: tuple[str, ...]
    declaration: AdapterCapabilityDeclaration
    production_validated: bool
    registered_from: str = ""

    @property
    def supports_live_execution(self) -> bool:
        """True only for adapters certified for live state mutation."""
        return self.production_validated


@dataclass(frozen=True)
class ContractValidation:
    """Outcome of validating one adapter against the V5 contract."""

    adapter_name: str
    problems: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return not self.problems


class RecoveryAdapterRegistry:
    """Fail-closed registry of recovery adapters and their capabilities.

    Registration is strict by default: an adapter with contract problems is
    rejected with :class:`AdapterContractError` and is never selectable by
    planners.  ``strict=False`` allows recording problems without raising,
    which is used by the certification lab to *report* broken adapters
    instead of crashing on them.
    """

    def __init__(self, *, strict: bool = True) -> None:
        self._strict = strict
        self._entries: dict[str, AdapterRegistration] = {}
        self._rejections: dict[str, ContractValidation] = {}

    # ------------------------------------------------------------------
    # Contract validation
    # ------------------------------------------------------------------

    @staticmethod
    def validate_contract(adapter: Any) -> ContractValidation:
        """Statically validate *adapter* against the V5 adapter contract."""
        problems: list[str] = []

        adapter_name = getattr(adapter, "adapter_name", "")
        adapter_type = getattr(adapter, "adapter_type", "")
        if not adapter_name or not str(adapter_name).strip():
            problems.append("adapter_name is missing or empty")
        if not adapter_type or not str(adapter_type).strip():
            problems.append("adapter_type is missing or empty")

        for method_name in REQUIRED_PROTOCOL_METHODS:
            method = getattr(adapter, method_name, None)
            if method is None or not callable(method):
                problems.append(f"protocol method '{method_name}' is not implemented")
                continue
            if not inspect.iscoroutinefunction(method):
                problems.append(f"protocol method '{method_name}' must be an async function")

        if isinstance(adapter, RecoveryAdapter):
            for method_name in REQUIRED_LEGACY_METHODS:
                method = getattr(adapter, method_name, None)
                if method is None or not callable(method):
                    problems.append(f"legacy method '{method_name}' is not implemented")

        capability = RecoveryAdapter.normalize_capability(
            getattr(adapter, "capability", "")
        )
        if capability not in {c.value for c in AdapterCapability}:
            problems.append(f"unknown capability value {capability!r}")

        return ContractValidation(
            adapter_name=str(adapter_name or "<unnamed>"),
            problems=tuple(problems),
        )

    async def _build_registration(
        self,
        adapter: Any,
        *,
        resource_kinds: tuple[str, ...],
        production_validated: bool | None = None,
        registered_from: str = "",
    ) -> AdapterRegistration:
        validation = self.validate_contract(adapter)
        if not validation.ok:
            self._rejections[validation.adapter_name] = validation
            if self._strict:
                raise AdapterContractError(
                    f"Adapter {validation.adapter_name!r} violates the recovery "
                    f"adapter contract: {'; '.join(validation.problems)}"
                )

        declaration: AdapterCapabilityDeclaration = await adapter.declare_capabilities()
        if not isinstance(declaration, AdapterCapabilityDeclaration):
            msg = (
                f"Adapter {getattr(adapter, 'adapter_name', '<unnamed>')!r} "
                "declare_capabilities() must return AdapterCapabilityDeclaration"
            )
            raise AdapterContractError(msg)

        adapter_name = str(adapter.adapter_name)
        if declaration.adapter_name != adapter_name:
            msg = (
                f"Adapter {adapter_name!r} declares capabilities under "
                f"{declaration.adapter_name!r}; declaration must match adapter_name"
            )
            raise AdapterContractError(msg)

        capability = RecoveryAdapter.normalize_capability(
            getattr(adapter, "capability", "")
        )
        if production_validated is None:
            production_validated = capability == AdapterCapability.PRODUCTION_VALIDATED.value

        return AdapterRegistration(
            adapter=adapter,
            adapter_name=adapter_name,
            adapter_type=str(adapter.adapter_type),
            capability=capability,
            resource_kinds=tuple(resource_kinds),
            declaration=declaration,
            production_validated=bool(production_validated),
            registered_from=registered_from,
        )

    # ------------------------------------------------------------------
    # Registration lifecycle
    # ------------------------------------------------------------------

    async def register(
        self,
        adapter: Any,
        *,
        resource_kinds: tuple[str, ...] = (),
        production_validated: bool | None = None,
        registered_from: str = "",
        replace: bool = False,
    ) -> AdapterRegistration:
        """Validate and register *adapter*.

        Raises :class:`AdapterContractError` when the contract is violated or
        when the name is already registered and ``replace`` is False.
        """
        if not resource_kinds:
            msg = (
                f"Adapter {getattr(adapter, 'adapter_name', '<unnamed>')!r} must "
                "declare at least one resource kind"
            )
            raise AdapterContractError(msg)

        registration = await self._build_registration(
            adapter,
            resource_kinds=resource_kinds,
            production_validated=production_validated,
            registered_from=registered_from,
        )
        if registration.adapter_name in self._entries and not replace:
            msg = f"Adapter {registration.adapter_name!r} is already registered"
            raise AdapterContractError(msg)
        self._entries[registration.adapter_name] = registration
        self._rejections.pop(registration.adapter_name, None)
        return registration

    def unregister(self, adapter_name: str) -> bool:
        """Remove an adapter from the registry.  Returns True if removed."""
        return self._entries.pop(adapter_name, None) is not None

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get(self, adapter_name: str) -> Any | None:
        entry = self._entries.get(adapter_name)
        return entry.adapter if entry else None

    def require(self, adapter_name: str) -> Any:
        entry = self._entries.get(adapter_name)
        if entry is None:
            msg = f"Adapter {adapter_name!r} is not registered"
            raise AdapterContractError(msg)
        return entry.adapter

    def registration(self, adapter_name: str) -> AdapterRegistration | None:
        return self._entries.get(adapter_name)

    def names(self) -> list[str]:
        return sorted(self._entries)

    def registrations(self) -> list[AdapterRegistration]:
        return [self._entries[name] for name in sorted(self._entries)]

    def adapters(self) -> list[Any]:
        return [entry.adapter for entry in self.registrations()]

    @property
    def rejections(self) -> dict[str, ContractValidation]:
        """Adapters that failed contract validation (strict mode only stores
        these when validation was performed through ``validate_contract``)."""
        return dict(self._rejections)

    def adapters_for_resource_kind(self, resource: str) -> list[Any]:
        """Return registered adapters whose declared resource-kind prefixes
        match *resource* (longest prefix first, then name order)."""
        matches: list[tuple[int, str, Any]] = []
        for name, entry in self._entries.items():
            for kind in entry.resource_kinds:
                if kind and resource.startswith(kind):
                    matches.append((-len(kind), name, entry.adapter))
                    break
        matches.sort()
        return [adapter for _, _, adapter in matches]

    async def select_for_action(self, action: Any) -> list[Any]:
        """Return every registered adapter that supports *action*.

        Ordering: production-validated adapters first, then registry
        insertion order, so planners prefer live-certified implementations.
        """
        supported: list[tuple[int, int, Any]] = []
        for index, entry in enumerate(self._entries.values()):
            try:
                if await entry.adapter.supports(action):
                    supported.append((0 if entry.production_validated else 1, index, entry.adapter))
            except Exception:  # noqa: BLE001, S112 - untrusted probe; a broken adapter is not a candidate
                continue
        supported.sort(key=lambda item: (item[0], item[1]))
        return [adapter for _, _, adapter in supported]

    async def capability_matrix(self) -> list[AdapterCapabilityDeclaration]:
        """Return capability declarations for every registered adapter."""
        return [entry.declaration for entry in self.registrations()]

    async def refresh_declaration(self, adapter_name: str) -> AdapterCapabilityDeclaration:
        """Re-read the capability declaration for a registered adapter."""
        entry = self._entries.get(adapter_name)
        if entry is None:
            msg = f"Adapter {adapter_name!r} is not registered"
            raise AdapterContractError(msg)
        declaration: AdapterCapabilityDeclaration = (
            await entry.adapter.declare_capabilities()
        )
        updated = AdapterRegistration(
            adapter=entry.adapter,
            adapter_name=entry.adapter_name,
            adapter_type=entry.adapter_type,
            capability=entry.capability,
            resource_kinds=entry.resource_kinds,
            declaration=declaration,
            production_validated=entry.production_validated,
            registered_from=entry.registered_from,
        )
        self._entries[adapter_name] = updated
        return declaration

    def clear(self) -> None:
        """Drop all registrations (used by tests and certification runs)."""
        self._entries.clear()
        self._rejections.clear()

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, adapter_name: object) -> bool:
        return adapter_name in self._entries
