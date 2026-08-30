from pydantic import BaseModel, ConfigDict


class SSOProviderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    provider_type: str
    status: str
    issuer: str | None = None
    authorization_url: str | None = None


class SSOAuthorizeRequest(BaseModel):
    provider_name: str


class SSOAuthorizeResponse(BaseModel):
    authorization_url: str
    state_token: str


class SSOCallbackRequest(BaseModel):
    state_token: str
    code: str | None = None


class SSOCallbackResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105
    refresh_token: str | None = None
