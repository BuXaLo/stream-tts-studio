"""Configuration storage for the Studio server."""
import os
from typing import Optional

from studio.core.storage import read_json, write_json_atomic


DEFAULT_CONFIG = {
    "host": "127.0.0.1",
    "port": 8765,
    "n_timesteps": 6,
    "auto_open_browser": True
}

DEFAULT_DA_CONFIG = {
    "enabled": False,
    "client_id": "",
    "client_secret": "",
    "streamerbot_url": "http://127.0.0.1:7474/DoAction",
    "streamerbot_action": "Donation"
}


class ConfigStore:
    def __init__(self, server_dir):
        self.config_file = os.path.join(server_dir, "config.json")
        self.da_config_file = os.path.join(server_dir, "da_config.json")
        self.da_tokens_file = os.path.join(server_dir, "da_tokens.json")

    def load_config(self) -> dict:
        cfg = read_json(self.config_file, DEFAULT_CONFIG, strict=False)
        return {**DEFAULT_CONFIG, **cfg} if isinstance(cfg, dict) else DEFAULT_CONFIG.copy()

    def save_config(self, cfg: dict):
        write_json_atomic(self.config_file, cfg)

    def load_da_config(self) -> dict:
        cfg = read_json(self.da_config_file, DEFAULT_DA_CONFIG, strict=False)
        return {**DEFAULT_DA_CONFIG, **cfg} if isinstance(cfg, dict) else DEFAULT_DA_CONFIG.copy()

    def save_da_config(self, cfg: dict):
        write_json_atomic(self.da_config_file, cfg)

    def load_da_tokens(self) -> Optional[dict]:
        tokens = read_json(self.da_tokens_file, None, strict=False)
        return tokens if isinstance(tokens, dict) else None

    def save_da_tokens(self, tokens: dict):
        write_json_atomic(self.da_tokens_file, tokens)
