"""Service for project manifest resolution, parsing, and fingerprinting."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from ai_sync.models import PROJECT_MANIFEST_FILENAMES, ProjectManifest


class ProjectManifestService:
    """Resolve, parse, and fingerprint project manifests."""

    def load_yaml_file(self, path: Path) -> dict[str, Any]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except (yaml.YAMLError, OSError) as exc:
            raise RuntimeError(f"Failed to load {path}: {exc}") from exc
        if data is None:
            return {}
        if not isinstance(data, dict):
            raise RuntimeError(f"Expected a mapping in {path}, got {type(data).__name__}")
        return data

    def manifest_fingerprint(self, path: Path) -> str:
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise RuntimeError(f"Failed to read {path}: {exc}") from exc
        return hashlib.sha256(content).hexdigest()

    def resolve_project_manifest_path(self, project_root: Path) -> Path:
        for filename in PROJECT_MANIFEST_FILENAMES:
            manifest_path = project_root / filename
            if manifest_path.exists():
                return manifest_path
        names = " or ".join(PROJECT_MANIFEST_FILENAMES)
        raise RuntimeError(f"No {names} found in {project_root}. Create one first.")

    def resolve_project_manifest(self, project_root: Path) -> ProjectManifest:
        manifest_path = self.resolve_project_manifest_path(project_root)
        data = self.load_yaml_file(manifest_path)
        try:
            return ProjectManifest.model_validate(data)
        except ValidationError as exc:
            raise RuntimeError(f"Invalid {manifest_path.name}: {exc}") from exc
