"""Requirement check result dataclass."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RequirementCheckResult:
    name: str
    ok: bool
    actual: str | None
    required: str
    error: str | None = None
