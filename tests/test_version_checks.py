import json
from pathlib import Path

from ai_sync.services.tool_version_service import ToolVersionService


def test_check_client_versions_matches_major_minor(monkeypatch, tmp_path: Path) -> None:
    service = ToolVersionService()
    lock = tmp_path / "versions.json"
    lock.write_text(json.dumps({"codex": "1.2.3"}), encoding="utf-8")
    monkeypatch.setattr(service, "detect_client_versions", lambda: {"codex": "1.2.99"})
    ok, _ = service.check_client_versions(lock)
    assert ok


def test_check_client_versions_mismatch(monkeypatch, tmp_path: Path) -> None:
    service = ToolVersionService()
    lock = tmp_path / "versions.json"
    lock.write_text(json.dumps({"codex": "1.2.3"}), encoding="utf-8")
    monkeypatch.setattr(service, "detect_client_versions", lambda: {"codex": "1.3.0"})
    ok, _ = service.check_client_versions(lock)
    assert ok
