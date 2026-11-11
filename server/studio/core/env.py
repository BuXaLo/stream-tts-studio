"""Portable runtime paths and environment bootstrap."""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler


def configure_environment(server_dir):
    server_dir = os.path.abspath(server_dir)
    base_dir = os.path.dirname(server_dir)
    cosy_dir = os.path.join(base_dir, "cosyvoice3")
    characters_dir = os.path.join(base_dir, "characters")
    fonts_dir = os.path.join(server_dir, "fonts")
    audio_tools_cache = os.path.join(cosy_dir, "pretrained_models", "audio_tools")
    paths = {
        "SERVER_DIR": server_dir,
        "BASE_DIR": base_dir,
        "COSY_DIR": cosy_dir,
        "CHARACTERS_DIR": characters_dir,
        "PRESETS_FILE": os.path.join(server_dir, "presets.json"),
        "ACTIVE_FILE": os.path.join(server_dir, "active_character.json"),
        "CONFIG_FILE": os.path.join(server_dir, "config.json"),
        "DA_CONFIG_FILE": os.path.join(server_dir, "da_config.json"),
        "DA_TOKENS_FILE": os.path.join(server_dir, "da_tokens.json"),
        "TEMP_DIR": os.path.join(server_dir, "temp"),
        "FFMPEG_PATH": os.path.join(cosy_dir, "tools", "ffmpeg.exe"),
        "FONTS_DIR": fonts_dir,
        "BUNDLED_FONTS_DIR": os.path.join(fonts_dir, "bundled"),
        "CUSTOM_FONTS_DIR": os.path.join(fonts_dir, "custom"),
        "AUDIO_TOOLS_CACHE": audio_tools_cache,
        "LOG_DIR": os.path.join(base_dir, "logs"),
        "DASHBOARD_DIR": os.path.join(base_dir, "web", "dashboard"),
        "OVERLAY_DIR": os.path.join(base_dir, "web", "overlay"),
    }
    for key in ("CHARACTERS_DIR", "TEMP_DIR", "BUNDLED_FONTS_DIR", "CUSTOM_FONTS_DIR", "AUDIO_TOOLS_CACHE", "LOG_DIR"):
        os.makedirs(paths[key], exist_ok=True)

    os.environ["TEMP"] = paths["TEMP_DIR"]
    os.environ["TMP"] = paths["TEMP_DIR"]
    os.environ["TORCH_HOME"] = audio_tools_cache
    os.environ["MODELSCOPE_CACHE"] = os.path.join(cosy_dir, "model_cache")
    os.environ["HF_HOME"] = os.path.join(cosy_dir, "model_cache")
    os.environ["MODELSCOPE_OFFLINE"] = "1"
    os.environ["MODELSCOPE_ENVIRONMENT"] = "local"
    os.environ["HF_HUB_OFFLINE"] = "1"

    if cosy_dir not in sys.path:
        sys.path.append(cosy_dir)

    logger = logging.getLogger("studio")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        file_handler = RotatingFileHandler(
            os.path.join(paths["LOG_DIR"], "studio.log"),
            maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
    paths["logger"] = logger
    return paths
