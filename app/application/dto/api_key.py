from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CreateApiKeyRequest(BaseModel):
    """Request payload for creating a new API key."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(default="API Key", min_length=1, max_length=255)
    expires_in_days: int | None = Field(default=None, gt=0, le=3650)
    expires_at: datetime | None = None

    @field_validator("expires_at")
    @classmethod
    def validate_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("expires_at must be timezone-aware.")
        return value

    @field_validator("expires_at")
    @classmethod
    def validate_not_past(cls, value: datetime | None) -> datetime | None:
        if value is not None and value <= datetime.now(value.tzinfo):
            raise ValueError("expires_at must be in the future.")
        return value


class ApiKeyResponse(BaseModel):
    """Public API key representation."""

    model_config = ConfigDict(from_attributes=True)

    key_id: str
    name: str
    expires_at: datetime
    created_at: datetime
    last_used_at: datetime | None = None
    revoked: bool = False
    revoked_at: datetime | None = None


class CreateApiKeyResponse(BaseModel):
    """Response returned immediately after key creation with the raw secret."""

    api_key: ApiKeyResponse
    raw_secret: str


class ApiKeyListResponse(BaseModel):
    """List of API keys for the current user."""

    api_keys: list[ApiKeyResponse]
