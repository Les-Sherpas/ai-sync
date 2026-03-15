"""Runtime requirement model."""

from pydantic import BaseModel, Field

from ai_sync.models.requirement_version import RequirementVersion


class Requirement(BaseModel):
    name: str
    servers: list[str] = Field(default_factory=list)
    version: RequirementVersion
