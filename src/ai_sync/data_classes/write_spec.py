"""Write spec dataclass."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WriteSpec:
    file_path: Path
    format: str
    target: str
    value: object
