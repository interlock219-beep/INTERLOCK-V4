from dataclasses import dataclass


@dataclass
class MFAEnableResponse:
    secret: str
    provisioning_uri: str
    backup_codes: list[str]


@dataclass
class MFAResponse:
    is_enabled: bool
    confirmed_at: str | None = None
