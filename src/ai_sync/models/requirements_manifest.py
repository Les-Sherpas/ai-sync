"""Requirements manifest model."""

from pydantic import BaseModel, Field

from ai_sync.models.requirement import Requirement


class RequirementsManifest(BaseModel):
    requirements: list[Requirement] = Field(default_factory=list)
