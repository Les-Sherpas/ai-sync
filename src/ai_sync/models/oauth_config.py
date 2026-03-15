"""OAuth server configuration model."""

from pydantic import BaseModel, Field


class OAuthConfig(BaseModel):
    enabled: bool = False
    clientId: str | None = None
    clientSecret: str | None = None
    authorizationUrl: str | None = None
    tokenUrl: str | None = None
    issuer: str | None = None
    redirectUri: str | None = None
    scopes: list[str] = Field(default_factory=list)
