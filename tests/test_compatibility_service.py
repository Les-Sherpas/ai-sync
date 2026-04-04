"""Tests for CompatibilityService."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ai_sync.data_classes.resolved_source import ResolvedSource
from ai_sync.models.project_manifest import ProjectManifest
from ai_sync.services.compatibility_service import CompatibilityService
from ai_sync.services.tool_version_service import ToolVersionService


def _make_service(tool_version_service: ToolVersionService | None = None) -> CompatibilityService:
    return CompatibilityService(
        tool_version_service=tool_version_service or ToolVersionService(),
    )


def _resolved_source(alias: str, root: Path, version: str | None = None) -> ResolvedSource:
    return ResolvedSource(
        alias=alias,
        source="https://example.com/repo.git",
        version=version,
        root=root,
        kind="remote",
        fingerprint="abc123",
    )


# -- check_manifest_schema --------------------------------------------------


def test_check_manifest_schema_supported_passes() -> None:
    service = _make_service()
    manifest = ProjectManifest(schema_version=2)
    service.check_manifest_schema(manifest)


def test_check_manifest_schema_unsupported_raises() -> None:
    service = _make_service()
    manifest = ProjectManifest(schema_version=99)
    with pytest.raises(RuntimeError, match="schema_version 99"):
        service.check_manifest_schema(manifest)


def test_check_manifest_schema_default_is_supported() -> None:
    service = _make_service()
    manifest = ProjectManifest()
    service.check_manifest_schema(manifest)


# -- check_source_compatibility ----------------------------------------------


def test_check_source_compatibility_satisfied(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "ai_sync.services.compatibility_service.get_ai_sync_version", lambda: "2.0.0"
    )
    source_root = tmp_path / "src"
    source_root.mkdir()
    (source_root / "ai-sync-source.yaml").write_text(
        'requires_ai_sync: ">=1.5.0"\n', encoding="utf-8"
    )
    service = _make_service()
    service.check_source_compatibility(
        {"myalias": _resolved_source("myalias", source_root, "v1.0.0")}
    )


def test_check_source_compatibility_unsatisfied_raises(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "ai_sync.services.compatibility_service.get_ai_sync_version", lambda: "1.5.0"
    )
    source_root = tmp_path / "src"
    source_root.mkdir()
    (source_root / "ai-sync-source.yaml").write_text(
        'requires_ai_sync: ">=2.0.0"\n', encoding="utf-8"
    )
    service = _make_service()
    with pytest.raises(RuntimeError, match="requires ai-sync >=2.0.0"):
        service.check_source_compatibility(
            {"myalias": _resolved_source("myalias", source_root, "v1.0.0")}
        )


def test_check_source_compatibility_missing_file_passes(tmp_path: Path) -> None:
    source_root = tmp_path / "src"
    source_root.mkdir()
    service = _make_service()
    service.check_source_compatibility(
        {"myalias": _resolved_source("myalias", source_root)}
    )


def test_check_source_compatibility_no_requires_field_passes(tmp_path: Path) -> None:
    source_root = tmp_path / "src"
    source_root.mkdir()
    (source_root / "ai-sync-source.yaml").write_text(
        "description: just metadata\n", encoding="utf-8"
    )
    service = _make_service()
    service.check_source_compatibility(
        {"myalias": _resolved_source("myalias", source_root)}
    )


def test_check_source_compatibility_invalid_specifier_raises(tmp_path: Path) -> None:
    source_root = tmp_path / "src"
    source_root.mkdir()
    (source_root / "ai-sync-source.yaml").write_text(
        'requires_ai_sync: "not a valid spec"\n', encoding="utf-8"
    )
    service = _make_service()
    with pytest.raises(RuntimeError, match="invalid requires_ai_sync specifier"):
        service.check_source_compatibility(
            {"myalias": _resolved_source("myalias", source_root)}
        )


def test_check_source_compatibility_error_message_includes_version(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "ai_sync.services.compatibility_service.get_ai_sync_version", lambda: "1.0.0"
    )
    source_root = tmp_path / "src"
    source_root.mkdir()
    (source_root / "ai-sync-source.yaml").write_text(
        'requires_ai_sync: ">=2.0.0"\n', encoding="utf-8"
    )
    service = _make_service()
    with pytest.raises(RuntimeError, match=r"Source 'myalias' \(v1\.2\.0\)"):
        service.check_source_compatibility(
            {"myalias": _resolved_source("myalias", source_root, "v1.2.0")}
        )


# -- check_client_versions ---------------------------------------------------


def test_check_client_versions_ok_no_warning() -> None:
    tvs = MagicMock(spec=ToolVersionService)
    tvs.get_default_versions_path.return_value = Path("/fake")
    tvs.check_client_versions.return_value = (True, "OK")
    display = MagicMock()

    service = _make_service(tvs)
    service.check_client_versions(display)
    display.print.assert_not_called()


def test_check_client_versions_drift_prints_warning() -> None:
    tvs = MagicMock(spec=ToolVersionService)
    tvs.get_default_versions_path.return_value = Path("/fake")
    tvs.check_client_versions.return_value = (True, "Version mismatch: cursor expected 2.5.x got 2.6.0")
    display = MagicMock()

    service = _make_service(tvs)
    service.check_client_versions(display)
    display.print.assert_called_once()
    assert "Version mismatch" in display.print.call_args[0][0]


def test_check_client_versions_failure_prints_warning() -> None:
    tvs = MagicMock(spec=ToolVersionService)
    tvs.get_default_versions_path.return_value = Path("/fake")
    tvs.check_client_versions.return_value = (False, "No client versions detected")
    display = MagicMock()

    service = _make_service(tvs)
    service.check_client_versions(display)
    display.print.assert_called_once()
    assert "No client versions detected" in display.print.call_args[0][0]
