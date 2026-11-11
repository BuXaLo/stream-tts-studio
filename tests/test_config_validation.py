import json
from pathlib import Path

from studio.core.config import ConfigStore, DEFAULT_CONFIG, DEFAULT_DA_CONFIG


def test_config_store_normalizes_invalid_legacy_values(tmp_path):
    store = ConfigStore(tmp_path)
    Path(store.config_file).write_text(json.dumps({
        "host": None, "port": True, "n_timesteps": 999, "auto_open_browser": "yes", "custom": "kept"
    }), encoding="utf-8")
    config = store.load_config()
    assert config["host"] == DEFAULT_CONFIG["host"]
    assert config["port"] == DEFAULT_CONFIG["port"]
    assert config["n_timesteps"] == 15
    assert config["auto_open_browser"] is DEFAULT_CONFIG["auto_open_browser"]
    assert config["custom"] == "kept"


def test_da_config_normalizes_invalid_legacy_values(tmp_path):
    store = ConfigStore(tmp_path)
    Path(store.da_config_file).write_text(json.dumps({
        "enabled": "true", "client_id": 123, "client_secret": None,
        "streamerbot_url": "ftp://localhost", "streamerbot_action": "[]"
    }), encoding="utf-8")
    config = store.load_da_config()
    assert config["enabled"] is DEFAULT_DA_CONFIG["enabled"]
    assert config["client_id"] == DEFAULT_DA_CONFIG["client_id"]
    assert config["client_secret"] == DEFAULT_DA_CONFIG["client_secret"]
    assert config["streamerbot_url"] == DEFAULT_DA_CONFIG["streamerbot_url"]
    assert config["streamerbot_action"] == DEFAULT_DA_CONFIG["streamerbot_action"]


def test_config_store_keeps_valid_full_port_range(tmp_path):
    store = ConfigStore(tmp_path)
    store.config_file.write_text(json.dumps({"port": 8765, "n_timesteps": 6}), encoding="utf-8")
    assert store.load_config()["port"] == 8765
