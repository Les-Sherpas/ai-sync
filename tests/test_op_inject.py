from __future__ import annotations

from pathlib import Path

from onepassword.defaults import DesktopAuth

from ai_sync.services.config_store_service import ConfigStoreService
from ai_sync.services.one_password_auth_service import OnePasswordAuthService
from ai_sync.services.one_password_secret_service import OnePasswordSecretService


class _FakeCliInjector:
    def inject(self, content: str, *, config_root: Path | None, environ: dict[str, str]) -> dict[str, str]:
        assert "B=op://vault/item/field" in content
        assert "D=op://vault/item/other" in content
        return {"B": "X", "D": "Y"}


class _FakeSdkResolver:
    def resolve_refs(
        self,
        *,
        refs: list[str],
        lines: list[str],
        line_to_ref: dict[int, str],
        config_root: Path | None,
        environ: dict[str, str],
    ) -> dict[str, str]:
        raise AssertionError("SDK fallback should not be used in this test")


def test_extract_and_inject_refs() -> None:
    service = OnePasswordSecretService(
        cli_injector=_FakeCliInjector(),  # type: ignore[arg-type]
        sdk_resolver=_FakeSdkResolver(),  # type: ignore[arg-type]
        environ={},
    )
    resolved = service.resolve(
        {
            "A": "1",
            "B": "op://vault/item/field",
            "D": "op://vault/item/other",
        }
    )
    assert resolved == {"A": "1", "B": "X", "D": "Y"}


def test_auth_resolver_prefers_token(monkeypatch) -> None:
    monkeypatch.setenv("OP_SERVICE_ACCOUNT_TOKEN", "token")
    monkeypatch.delenv("OP_ACCOUNT", raising=False)
    resolver = OnePasswordAuthService(config_store_service=ConfigStoreService())
    assert resolver.resolve_auth(None, {"OP_SERVICE_ACCOUNT_TOKEN": "token"}) == "token"


def test_auth_resolver_uses_account(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("OP_SERVICE_ACCOUNT_TOKEN", raising=False)
    monkeypatch.setenv("OP_ACCOUNT", "acc")
    resolver = OnePasswordAuthService(config_store_service=ConfigStoreService())
    auth = resolver.resolve_auth(tmp_path, {"OP_ACCOUNT": "acc"})
    assert isinstance(auth, DesktopAuth)
    assert auth.account_name == "acc"
