"""Recovery adapter factory.

Builds the list of enabled recovery adapters from application settings.
Production deployments should configure ``RECOVERY_ADAPTER_NAMES`` explicitly.
"""

from __future__ import annotations

from app.domain.services.recovery_adapter import RecoveryAdapter
from app.infrastructure.config.settings import get_settings
from app.infrastructure.recovery.database_recovery_adapter import DatabaseRecoveryAdapter
from app.infrastructure.recovery.git_repository_adapter import GitRepositoryAdapter

_ADAPTER_REGISTRY: dict[str, type[RecoveryAdapter]] = {
    "database_recovery": DatabaseRecoveryAdapter,
    "git_repository": GitRepositoryAdapter,
}


def build_recovery_adapters() -> list[RecoveryAdapter]:
    """Return enabled recovery adapters based on ``RECOVERY_ADAPTER_NAMES``.

    Adapters that require external configuration (e.g. database paths) are
    only included when their name appears in the setting.
    """
    settings = get_settings()
    names = [name.strip() for name in settings.recovery_adapter_names if name.strip()]
    adapters: list[RecoveryAdapter] = []
    for name in names:
        adapter_cls = _ADAPTER_REGISTRY.get(name)
        if adapter_cls is not None:
            adapters.append(adapter_cls())
    return adapters
