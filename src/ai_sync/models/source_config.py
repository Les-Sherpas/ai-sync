"""Source configuration model."""

from pydantic import BaseModel


class SourceConfig(BaseModel):
    source: str
    version: str | None = None
