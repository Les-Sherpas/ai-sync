"""Plan source model."""

from pydantic import BaseModel


class PlanSource(BaseModel):
    alias: str
    source: str
    version: str | None = None
    kind: str
    fingerprint: str
    portability_warning: str | None = None
