"""OAuth override model for client-specific settings."""

from pydantic import BaseModel


class OAuthOverrideConfig(BaseModel):
    """OAuth config used inside client overrides."""

    enabled: bool | None = None
    clientId: str | None = None
    clientSecret: str | None = None
    authorizationUrl: str | None = None
    tokenUrl: str | None = None
    issuer: str | None = None
    redirectUri: str | None = None
    scopes: list[str] | None = None
