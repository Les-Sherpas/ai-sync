"""Pydantic models for MCP server manifest validation."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, field_validator, model_validator


class OAuthConfig(BaseModel):
    enabled: bool = False
    clientId: str | None = None
    clientSecret: str | None = None
    authorizationUrl: str | None = None
    tokenUrl: str | None = None
    issuer: str | None = None
    redirectUri: str | None = None
    scopes: list[str] = Field(default_factory=list)


class OAuthOverrideConfig(BaseModel):
    """OAuth config for use inside ClientOverrideConfig.

    `enabled` and `scopes` use None as their sentinel so that an override
    that doesn't mention them doesn't silently reset the base values (which
    OAuthConfig serializes as False and [] respectively).
    """

    enabled: bool | None = None
    clientId: str | None = None
    clientSecret: str | None = None
    authorizationUrl: str | None = None
    tokenUrl: str | None = None
    issuer: str | None = None
    redirectUri: str | None = None
    scopes: list[str] | None = None


class ClientOverrideConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: Literal["stdio", "http", "sse"] | None = None
    command: str | None = None
    args: list[str] | None = None
    url: str | None = None
    env: dict[str, str] | None = None
    auth: dict[str, str] | None = None
    oauth: OAuthOverrideConfig | None = None
    headers: dict[str, str] | None = None
    auth_provider_type: str | None = None
    description: str | None = None
    trust: bool | None = None
    timeout_seconds: StrictInt | StrictFloat | None = None


class ServerConfig(BaseModel):
    method: Literal["stdio", "http", "sse"] = "stdio"
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    url: str | None = None
    description: str | None = None
    trust: bool | None = None
    timeout_seconds: StrictInt | StrictFloat | None = None
    env: dict[str, str] = Field(default_factory=dict)
    auth: dict[str, str] = Field(default_factory=dict)
    oauth: OAuthConfig = Field(default_factory=OAuthConfig)
    headers: dict[str, str] = Field(default_factory=dict)
    auth_provider_type: str | None = None
    client_overrides: dict[str, ClientOverrideConfig] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def reject_legacy_timeout(cls, data):
        if isinstance(data, dict) and "timeout" in data:
            raise ValueError("timeout is no longer supported; use timeout_seconds")
        return data

    @field_validator("command")
    @classmethod
    def validate_command_for_stdio(cls, value: str | None, info):
        method = info.data.get("method", "stdio")
        if method == "stdio" and (value is None or not str(value).strip()):
            raise ValueError("stdio servers must define command")
        return value

    @field_validator("timeout_seconds")
    @classmethod
    def validate_timeout_seconds(cls, value: int | float | None):
        if value is None:
            return value
        if value < 0:
            raise ValueError("timeout_seconds must be >= 0")
        return value


class MCPManifest(BaseModel):
    servers: dict[str, ServerConfig] = Field(default_factory=dict)


class RequirementVersion(BaseModel):
    require: str
    get_cmd: str | None = None

    @field_validator("require")
    @classmethod
    def require_must_have_known_prefix(cls, v: str) -> str:
        if not v.startswith(("~", "^")):
            raise ValueError(f"require must start with '~' or '^', got: {v!r}")
        if not re.fullmatch(r"\d+\.\d+\.\d+", v[1:]):
            raise ValueError(f"require must be ~X.Y.Z or ^X.Y.Z, got: {v!r}")
        return v


class Requirement(BaseModel):
    name: str
    servers: list[str] = Field(default_factory=list)
    version: RequirementVersion


class RequirementsManifest(BaseModel):
    requirements: list[Requirement] = Field(default_factory=list)
