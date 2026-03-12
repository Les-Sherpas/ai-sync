from __future__ import annotations

from pathlib import Path

from ai_sync import op_inject


def test_extract_and_inject_refs() -> None:
    lines = ["A=1", "B=op://vault/item/field", "# C=op://skip", "D=op://vault/item/other"]
    refs, mapping = op_inject._extract_op_refs(lines)
    assert refs == ["op://vault/item/field", "op://vault/item/other"]
    injected = op_inject._inject_resolved(lines, mapping, {"op://vault/item/field": "X"})
    assert "B=X" in injected
    assert "D=op://vault/item/other" in injected


def test_resolve_auth_prefers_token(monkeypatch) -> None:
    monkeypatch.setenv("OP_SERVICE_ACCOUNT_TOKEN", "token")
    monkeypatch.delenv("OP_ACCOUNT", raising=False)
    assert op_inject._resolve_auth(None) == "token"


def test_resolve_auth_uses_account(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("OP_SERVICE_ACCOUNT_TOKEN", raising=False)
    monkeypatch.setenv("OP_ACCOUNT", "acc")
    auth = op_inject._resolve_auth(tmp_path)
    assert isinstance(auth, op_inject.DesktopAuth)
    assert auth.account_name == "acc"
