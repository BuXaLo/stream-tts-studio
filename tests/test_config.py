from studio.core.config import ConfigStore, DEFAULT_CONFIG, DEFAULT_DA_CONFIG


def test_config_store_defaults_and_roundtrip(tmp_path):
    store = ConfigStore(tmp_path)
    assert store.load_config() == DEFAULT_CONFIG
    assert store.load_da_config() == DEFAULT_DA_CONFIG
    assert store.load_da_tokens() is None

    store.save_config({"host": "localhost", "port": 8765})
    store.save_da_config({"enabled": True, "client_id": "client"})
    store.save_da_tokens({"access_token": "token"})

    assert store.load_config()["host"] == "localhost"
    assert store.load_da_config()["enabled"] is True
    assert store.load_da_tokens() == {"access_token": "token"}
