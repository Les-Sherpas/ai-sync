"""Resolved source dataclass."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ResolvedSource:
    alias: str
    source: str
    version: str | None
    root: Path
    kind: str
    fingerprint: str
    portability_warning: str | None = None
