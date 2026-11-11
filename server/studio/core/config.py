"""Configuration storage for the Studio server."""
import json
import os
from typing import Optional

from studio.core.storage import read_json, write_json_atomic
from studio.core.validation import is_valid_bind_host, validate_http_url, validate_port


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
        raw = read_json(self.config_file, DEFAULT_CONFIG, strict=False)
        cfg = {**DEFAULT_CONFIG, **raw} if isinstance(raw, dict) else DEFAULT_CONFIG.copy()
        if not is_valid_bind_host(cfg.get("host")):
            cfg["host"] = DEFAULT_CONFIG["host"]
        try:
            cfg["port"] = validate_port(cfg.get("port"))
        except ValueError:
            cfg["port"] = DEFAULT_CONFIG["port"]
        try:
            steps = validate_port(cfg.get("n_timesteps"))
            cfg["n_timesteps"] = max(4, min(15, steps))
        except ValueError:
            cfg["n_timesteps"] = DEFAULT_CONFIG["n_timesteps"]
        if not isinstance(cfg.get("auto_open_browser"), bool):
            cfg["auto_open_browser"] = DEFAULT_CONFIG["auto_open_browser"]
        return cfg

    def save_config(self, cfg: dict):
        write_json_atomic(self.config_file, cfg)

    def load_da_config(self) -> dict:
        raw = read_json(self.da_config_file, DEFAULT_DA_CONFIG, strict=False)
        cfg = {**DEFAULT_DA_CONFIG, **raw} if isinstance(raw, dict) else DEFAULT_DA_CONFIG.copy()
        if not isinstance(cfg.get("enabled"), bool):
            cfg["enabled"] = DEFAULT_DA_CONFIG["enabled"]
        for key in ("client_id", "client_secret"):
            if not isinstance(cfg.get(key), str):
                cfg[key] = DEFAULT_DA_CONFIG[key]
        try:
            cfg["streamerbot_url"] = validate_http_url(cfg.get("streamerbot_url"))
        except ValueError:
            cfg["streamerbot_url"] = DEFAULT_DA_CONFIG["streamerbot_url"]
        action = cfg.get("streamerbot_action")
        if not isinstance(action, str) or not action.strip():
            cfg["streamerbot_action"] = DEFAULT_DA_CONFIG["streamerbot_action"]
        else:
            action = action.strip()
            if action.startswith(("{", "[")):
                try:
                    parsed_action = json.loads(action)
                except ValueError:
                    parsed_action = None
                if not isinstance(parsed_action, dict):
                    action = DEFAULT_DA_CONFIG["streamerbot_action"]
            cfg["streamerbot_action"] = action
        return cfg

    def save_da_config(self, cfg: dict):
        write_json_atomic(self.da_config_file, cfg)

    def load_da_tokens(self) -> Optional[dict]:
        tokens = read_json(self.da_tokens_file, None, strict=False)
        return tokens if isinstance(tokens, dict) else None

    def save_da_tokens(self, tokens: dict):
        write_json_atomic(self.da_tokens_file, tokens)
