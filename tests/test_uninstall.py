from __future__ import annotations

import json
from pathlib import Path

import tomli
import yaml

from ai_sync.adapters.state_store import StateStore
from ai_sync.data_classes.write_spec import WriteSpec
from ai_sync.di import create_container


def _track_write(specs: list[WriteSpec], store: StateStore) -> None:
    container = create_container()
    container.managed_output_service().track_write_blocks(specs, store)


def _run_uninstall(project_root: Path, *, apply: bool) -> int:
    container = create_container()
    return container.uninstall_service().run_uninstall(project_root, apply=apply)

# ---------------------------------------------------------------------------
# Text marker uninstall
# ---------------------------------------------------------------------------


def test_uninstall_removes_marker_block(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    store = StateStore(tmp_path)
    target = tmp_path / ".gemini" / "GEMINI.md"
    spec = WriteSpec(
        file_path=target,
        format="text",
        target="ai-sync:mcp-instructions",
        value="## MCP\n\nUse work\n",
    )
    _track_write([spec], store)
    assert target.exists()
    assert "BEGIN ai-sync:mcp-instructions" in target.read_text(encoding="utf-8")

    _run_uninstall(tmp_path, apply=True)
    if target.exists():
        assert "BEGIN ai-sync:mcp-instructions" not in target.read_text(encoding="utf-8")


def test_uninstall_text_restores_baseline(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    store = StateStore(tmp_path)
    target = tmp_path / "rules.mdc"
    target.parent.mkdir(parents=True, exist_ok=True)
    original_block = "<!-- BEGIN ai-sync:test -->\noriginal content\n<!-- END ai-sync:test -->"
    target.write_text(f"# Header\n\n{original_block}\n", encoding="utf-8")

    _track_write(
        [
            WriteSpec(file_path=target, format="text", target="ai-sync:test", value="replaced content"),
        ],
        store
    )
    assert "replaced content" in target.read_text(encoding="utf-8")

    _run_uninstall(tmp_path, apply=True)
    restored = target.read_text(encoding="utf-8")
    assert "original content" in restored
    assert "replaced content" not in restored


# ---------------------------------------------------------------------------
# Structured JSON uninstall
# ---------------------------------------------------------------------------


def test_uninstall_structured_json_roundtrip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    store = StateStore(tmp_path)
    target = tmp_path / "config.json"
    _track_write(
        [
            WriteSpec(file_path=target, format="json", target="/settings/theme", value="dark"),
            WriteSpec(file_path=target, format="json", target="/settings/lang", value="en"),
        ],
        store
    )
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["settings"]["theme"] == "dark"
    assert data["settings"]["lang"] == "en"

    _run_uninstall(tmp_path, apply=True)
    data = json.loads(target.read_text(encoding="utf-8"))
    assert "theme" not in data.get("settings", {})
    assert "lang" not in data.get("settings", {})


def test_uninstall_structured_json_preserves_pre_existing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    store = StateStore(tmp_path)
    target = tmp_path / "config.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('{"existing": true}', encoding="utf-8")

    _track_write(
        [
            WriteSpec(file_path=target, format="json", target="/added", value="new"),
        ],
        store
    )
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["existing"] is True
    assert data["added"] == "new"

    _run_uninstall(tmp_path, apply=True)
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data.get("existing") is True
    assert "added" not in data


def test_uninstall_structured_json_restores_overwritten_value(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    store = StateStore(tmp_path)
    target = tmp_path / "config.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('{"key": "original"}', encoding="utf-8")

    _track_write(
        [
            WriteSpec(file_path=target, format="json", target="/key", value="replaced"),
        ],
        store
    )
    assert json.loads(target.read_text(encoding="utf-8"))["key"] == "replaced"

    _run_uninstall(tmp_path, apply=True)
    assert json.loads(target.read_text(encoding="utf-8"))["key"] == "original"


# ---------------------------------------------------------------------------
# Structured YAML uninstall
# ---------------------------------------------------------------------------


def test_uninstall_structured_yaml_roundtrip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    store = StateStore(tmp_path)
    target = tmp_path / "config.yaml"
    _track_write(
        [
            WriteSpec(file_path=target, format="yaml", target="/servers/main/port", value=8080),
        ],
        store
    )
    data = yaml.safe_load(target.read_text(encoding="utf-8"))
    assert data["servers"]["main"]["port"] == 8080

    _run_uninstall(tmp_path, apply=True)
    data = yaml.safe_load(target.read_text(encoding="utf-8"))
    assert "port" not in data.get("servers", {}).get("main", {})


# ---------------------------------------------------------------------------
# Structured TOML uninstall
# ---------------------------------------------------------------------------


def test_uninstall_structured_toml_roundtrip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    store = StateStore(tmp_path)
    target = tmp_path / "config.toml"
    _track_write(
        [
            WriteSpec(file_path=target, format="toml", target="/tool/name", value="ai-sync"),
        ],
        store
    )
    data = tomli.loads(target.read_text(encoding="utf-8"))
    assert data["tool"]["name"] == "ai-sync"

    _run_uninstall(tmp_path, apply=True)
    data = tomli.loads(target.read_text(encoding="utf-8"))
    assert "name" not in data.get("tool", {})


# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------


def test_uninstall_dry_run_does_not_modify(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    store = StateStore(tmp_path)
    target = tmp_path / "config.json"
    _track_write(
        [
            WriteSpec(file_path=target, format="json", target="/key", value="val"),
        ],
        store
    )
    assert target.exists()
    content_before = target.read_text(encoding="utf-8")

    _run_uninstall(tmp_path, apply=False)
    assert target.read_text(encoding="utf-8") == content_before


# ---------------------------------------------------------------------------
# Empty state
# ---------------------------------------------------------------------------


def test_uninstall_empty_state_returns_zero(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    result = _run_uninstall(tmp_path, apply=True)
    assert result == 0


# ---------------------------------------------------------------------------
# Root-list JSON uninstall
# ---------------------------------------------------------------------------


def test_uninstall_structured_json_root_list(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    store = StateStore(tmp_path)
    target = tmp_path / "list.json"
    _track_write(
        [
            WriteSpec(file_path=target, format="json", target="/", value=[]),
            WriteSpec(file_path=target, format="json", target="/0", value={"name": "alpha"}),
        ],
        store
    )
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data == [{"name": "alpha"}]

    _run_uninstall(tmp_path, apply=True)
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data == {}
