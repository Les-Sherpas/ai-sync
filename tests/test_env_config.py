from __future__ import annotations

from pathlib import Path

import pytest

from ai_sync.env_config import EnvVarConfig, load_env_config, read_existing_env_file


def test_load_env_config_global_and_local(tmp_path: Path) -> None:
    env_yaml = tmp_path / "env.yaml"
    env_yaml.write_text(
        "TOKEN:\n  value: abc\nSECRET:\n  scope: local\n  description: personal secret\n",
        encoding="utf-8",
    )
    config = load_env_config(env_yaml)
    assert config["TOKEN"].value == "abc"
    assert config["TOKEN"].scope == "global"
    assert config["SECRET"].scope == "local"
    assert config["SECRET"].value is None
    assert config["SECRET"].description == "personal secret"


def test_load_env_config_shorthand_string_value(tmp_path: Path) -> None:
    env_yaml = tmp_path / "env.yaml"
    env_yaml.write_text("TOKEN: abc\n", encoding="utf-8")
    config = load_env_config(env_yaml)
    assert config["TOKEN"].value == "abc"
    assert config["TOKEN"].scope == "global"


def test_load_env_config_global_missing_value(tmp_path: Path) -> None:
    env_yaml = tmp_path / "env.yaml"
    env_yaml.write_text("TOKEN:\n  scope: global\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Global-scoped env vars must have a value"):
        load_env_config(env_yaml)


def test_load_env_config_local_with_value(tmp_path: Path) -> None:
    env_yaml = tmp_path / "env.yaml"
    env_yaml.write_text("TOKEN:\n  scope: local\n  value: oops\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Local-scoped env vars must not have a value"):
        load_env_config(env_yaml)


def test_load_env_config_invalid_yaml(tmp_path: Path) -> None:
    env_yaml = tmp_path / "env.yaml"
    env_yaml.write_text(":\n  bad yaml {{{\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Failed to parse"):
        load_env_config(env_yaml)


def test_load_env_config_not_a_mapping(tmp_path: Path) -> None:
    env_yaml = tmp_path / "env.yaml"
    env_yaml.write_text("- item1\n- item2\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="expected a mapping"):
        load_env_config(env_yaml)


def test_load_env_config_null_entry(tmp_path: Path) -> None:
    env_yaml = tmp_path / "env.yaml"
    env_yaml.write_text("TOKEN:\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Invalid env.yaml entry"):
        load_env_config(env_yaml)


def test_load_env_config_empty_file(tmp_path: Path) -> None:
    env_yaml = tmp_path / "env.yaml"
    env_yaml.write_text("", encoding="utf-8")
    assert load_env_config(env_yaml) == {}


def test_read_existing_env_file_with_values(tmp_path: Path) -> None:
    (tmp_path / ".env.ai-sync").write_text("A=1\nB=hello\n", encoding="utf-8")
    result = read_existing_env_file(tmp_path)
    assert result == {"A": "1", "B": "hello"}


def test_read_existing_env_file_missing(tmp_path: Path) -> None:
    assert read_existing_env_file(tmp_path) == {}


def test_read_existing_env_file_empty(tmp_path: Path) -> None:
    (tmp_path / ".env.ai-sync").write_text("", encoding="utf-8")
    assert read_existing_env_file(tmp_path) == {}


def test_env_var_config_op_ref() -> None:
    cfg = EnvVarConfig(value="op://Vault/Item/field")
    assert cfg.scope == "global"
    assert cfg.value == "op://Vault/Item/field"


def test_env_var_config_description_optional() -> None:
    cfg = EnvVarConfig(value="plain")
    assert cfg.description is None
