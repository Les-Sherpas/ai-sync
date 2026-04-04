"""Service for version and compatibility checks across ai-sync, manifests, and sources."""

from __future__ import annotations

from pathlib import Path

import yaml
from packaging.specifiers import InvalidSpecifier, SpecifierSet

from ai_sync.data_classes.resolved_source import ResolvedSource
from ai_sync.models.project_manifest import SUPPORTED_MANIFEST_SCHEMAS, ProjectManifest
from ai_sync.models.source_metadata import SourceMetadata
from ai_sync.services.display_service import DisplayService
from ai_sync.services.tool_version_service import ToolVersionService
from ai_sync.version import get_ai_sync_version

SOURCE_METADATA_FILENAME = "ai-sync-source.yaml"


class CompatibilityService:
    """Centralised version and compatibility checks.

    Absorbs the client-version-drift warning previously duplicated in
    PlanService and ApplyService, and adds manifest schema and source
    compatibility gates.
    """

    def __init__(self, *, tool_version_service: ToolVersionService) -> None:
        self._tool_version_service = tool_version_service

    def check_client_versions(self, display: DisplayService) -> None:
        """Warn (non-fatal) when installed AI-client versions drift from the lock file."""
        versions_path = self._tool_version_service.get_default_versions_path()
        ok, message = self._tool_version_service.check_client_versions(versions_path)
        if not ok or message != "OK":
            display.print(f"Warning: {message}", style="warning")

    def check_manifest_schema(self, manifest: ProjectManifest) -> None:
        """Hard-fail if the manifest declares a schema version this ai-sync does not support."""
        if manifest.schema_version not in SUPPORTED_MANIFEST_SCHEMAS:
            ai_sync_version = get_ai_sync_version()
            supported = ", ".join(str(v) for v in sorted(SUPPORTED_MANIFEST_SCHEMAS))
            raise RuntimeError(
                f"Manifest uses schema_version {manifest.schema_version}, "
                f"but this ai-sync ({ai_sync_version}) supports {{{supported}}}. "
                f"Upgrade ai-sync."
            )

    def check_source_compatibility(
        self, resolved_sources: dict[str, ResolvedSource]
    ) -> None:
        """Hard-fail if any resolved source requires a newer ai-sync than the running version."""
        ai_sync_version = get_ai_sync_version()
        for alias, source in resolved_sources.items():
            metadata = self._load_source_metadata(source.root)
            if metadata is None or metadata.requires_ai_sync is None:
                continue
            try:
                specifier = SpecifierSet(metadata.requires_ai_sync)
            except InvalidSpecifier as exc:
                raise RuntimeError(
                    f"Source {alias!r} has invalid requires_ai_sync specifier "
                    f"{metadata.requires_ai_sync!r}: {exc}"
                ) from exc
            if ai_sync_version not in specifier:
                version_label = f" ({source.version})" if source.version else ""
                raise RuntimeError(
                    f"Source {alias!r}{version_label} requires ai-sync "
                    f"{metadata.requires_ai_sync}, but the installed version is "
                    f"{ai_sync_version}. Upgrade ai-sync."
                )

    @staticmethod
    def _load_source_metadata(root: Path) -> SourceMetadata | None:
        path = root / SOURCE_METADATA_FILENAME
        if not path.is_file():
            return None
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            return None
        if not isinstance(raw, dict):
            return None
        return SourceMetadata.model_validate(raw)
