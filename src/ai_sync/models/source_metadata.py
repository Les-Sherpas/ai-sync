"""Model for ai-sync-source.yaml metadata at the root of config source repos."""

from __future__ import annotations

from pydantic import BaseModel


class SourceMetadata(BaseModel):
    """Metadata declared by a config source repo in ``ai-sync-source.yaml``."""

    requires_ai_sync: str | None = None
