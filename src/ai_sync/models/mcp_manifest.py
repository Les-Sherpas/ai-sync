"""MCP manifest model."""

from pydantic import BaseModel, Field

from ai_sync.models.server_config import ServerConfig


class MCPManifest(BaseModel):
    servers: dict[str, ServerConfig] = Field(default_factory=dict)
