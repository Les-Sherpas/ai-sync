"""State entry dataclass."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class StateEntry:
    file_path: str
    format: str
    target: str
    baseline: dict
