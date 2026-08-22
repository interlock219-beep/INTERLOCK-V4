from dataclasses import dataclass


@dataclass
class SessionResponse:
    session_id: str
    device_info: str
    ip_address: str
    created_at: str
    last_used_at: str
    expires_at: str


@dataclass
class TokenRefreshRequest:
    refresh_token: str


@dataclass
class TokenRefreshResponse:
    access_token: str
    refresh_token: str
    expires_in: int
