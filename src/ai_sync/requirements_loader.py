"""Requirements manifest loading and filtering."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from .display import Display
from .models import Requirement, RequirementsManifest


def _load_requirements(repo_root: Path, display: Display) -> list[Requirement]:
    requirements_path = repo_root / "requirements.yaml"
    if not requirements_path.exists():
        return []
    try:
        with open(requirements_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except (yaml.YAMLError, OSError) as exc:
        display.print(f"Failed to load {requirements_path}: {exc}", style="warning")
        return []
    try:
        model = RequirementsManifest.model_validate(data)
    except ValidationError as exc:
        raise RuntimeError(f"requirements.yaml validation failed: {exc}") from exc
    return model.requirements


def load_and_filter_requirements(
    repo_roots: list[Path],
    enabled_server_ids: list[str],
    display: Display,
) -> list[Requirement]:
    merged: dict[str, Requirement] = {}
    for repo_root in repo_roots:
        for req in _load_requirements(repo_root, display):
            merged[req.name] = req
    enabled_set = set(enabled_server_ids)
    return [req for req in merged.values() if set(req.servers) & enabled_set]
