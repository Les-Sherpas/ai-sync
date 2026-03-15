"""Service for project root discovery."""

from __future__ import annotations

from pathlib import Path

from ai_sync.models import PROJECT_MANIFEST_FILENAMES


class ProjectLocatorService:
    """Walk the filesystem upward to find the project root."""

    def find_project_root(self, start: Path | None = None) -> Path | None:
        current = (start or Path.cwd()).resolve()
        while True:
            if any((current / filename).exists() for filename in PROJECT_MANIFEST_FILENAMES):
                return current
            parent = current.parent
            if parent == current:
                return None
            current = parent
