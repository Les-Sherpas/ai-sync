from ai_sync.services.config_store_service import ConfigStoreService


def test_write_and_load_config(tmp_path) -> None:
    service = ConfigStoreService()
    data = {"op_account_identifier": "example.1password.com", "secret_provider": "1password"}
    service.write_config(data, tmp_path)
    loaded = service.load_config(tmp_path)
    assert loaded["op_account_identifier"] == "example.1password.com"


def test_resolve_op_account_identifier_prefers_env(monkeypatch, tmp_path) -> None:
    service = ConfigStoreService()
    service.write_config(
        {"op_account_identifier": "from-config.1password.com", "secret_provider": "1password"},
        tmp_path,
    )
    monkeypatch.setenv("OP_ACCOUNT", "FromEnv")
    assert ConfigStoreService(environ={"OP_ACCOUNT": "FromEnv"}).resolve_op_account_identifier(tmp_path) == "FromEnv"


def test_resolve_op_account_identifier_from_config(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("OP_ACCOUNT", raising=False)
    service = ConfigStoreService(environ={})
    service.write_config(
        {"op_account_identifier": "from-config.1password.com", "secret_provider": "1password"},
        tmp_path,
    )
    assert service.resolve_op_account_identifier(tmp_path) == "from-config.1password.com"
