# -*- coding: utf-8 -*-
import os
import sys
import ipaddress
import secrets
import html
import math
SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)
import io
import re
import gc
import json
import time
import wave
import base64
import shutil
import threading
import subprocess
import webbrowser
import logging
import asyncio
import urllib.parse
from typing import Optional

import requests
import websockets

from studio.core.storage import StorageError, get_file_lock, read_json, write_json_atomic, write_bytes_atomic
from studio.core.config import ConfigStore
from studio.core.ws import ConnectionManager, ws_manager
from studio.services.text import has_speakable_content, num_to_ru_words, sanitize_overlay_text, sanitize_text
from studio.core.validation import is_valid_bind_host, same_origin
from studio.core.validation import validate_port
from studio.services.da_worker import DA_AUTH_URL, DA_SCOPES, DA_TOKEN_URL, DonationAlertsWorker, configure_worker

# Подавляем назойливые DEBUG логи multipart и websockets в консоли
logging.getLogger("multipart").setLevel(logging.WARNING)
logging.getLogger("websockets").setLevel(logging.WARNING)

class EndpointFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return "GET /api/system_config" not in msg and "GET /api/da/config" not in msg

logging.getLogger("uvicorn.access").addFilter(EndpointFilter())

# ==================== ПУТИ И ОКРУЖЕНИЕ ====================
SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SERVER_DIR)

COSY_DIR = os.path.join(BASE_DIR, "cosyvoice3")
CHARACTERS_DIR = os.path.join(BASE_DIR, "characters")
PRESETS_FILE = os.path.join(SERVER_DIR, "presets.json")
ACTIVE_FILE = os.path.join(SERVER_DIR, "active_character.json")
CONFIG_FILE = os.path.join(SERVER_DIR, "config.json")
DA_CONFIG_FILE = os.path.join(SERVER_DIR, "da_config.json")
DA_TOKENS_FILE = os.path.join(SERVER_DIR, "da_tokens.json")
TEMP_DIR = os.path.join(SERVER_DIR, "temp")
FFMPEG_PATH = os.path.join(COSY_DIR, "tools", "ffmpeg.exe")

FONTS_DIR = os.path.join(SERVER_DIR, "fonts")
BUNDLED_FONTS_DIR = os.path.join(FONTS_DIR, "bundled")
CUSTOM_FONTS_DIR = os.path.join(FONTS_DIR, "custom")

AUDIO_TOOLS_CACHE = os.path.join(COSY_DIR, "pretrained_models", "audio_tools")

os.makedirs(CHARACTERS_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(BUNDLED_FONTS_DIR, exist_ok=True)
os.makedirs(CUSTOM_FONTS_DIR, exist_ok=True)
os.makedirs(AUDIO_TOOLS_CACHE, exist_ok=True)
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logger = logging.getLogger("studio")
logger.setLevel(logging.INFO)
if not logger.handlers:
    from logging.handlers import RotatingFileHandler
    log_formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    file_handler = RotatingFileHandler(os.path.join(LOG_DIR, "studio.log"), maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(log_formatter)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

os.environ["TEMP"] = TEMP_DIR
os.environ["TMP"] = TEMP_DIR
os.environ["TORCH_HOME"] = AUDIO_TOOLS_CACHE
os.environ["MODELSCOPE_CACHE"] = os.path.join(COSY_DIR, "model_cache")
os.environ["HF_HOME"] = os.path.join(COSY_DIR, "model_cache")
os.environ["MODELSCOPE_OFFLINE"] = "1"
os.environ["MODELSCOPE_ENVIRONMENT"] = "local"
os.environ["HF_HUB_OFFLINE"] = "1"

if COSY_DIR not in sys.path:
    sys.path.append(COSY_DIR)

import numpy as np
import torch
import torchaudio
import soundfile as sf
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import Response, FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from faster_whisper import WhisperModel
from cosyvoice.cli.cosyvoice import AutoModel

logger.info("=" * 60)
logger.info("TTS STUDIO & OVERLAY BACKEND (CosyVoice 3 + Whisper + Demucs + DA)")
logger.info("=" * 60)

WHISPER_PATH = os.path.join(COSY_DIR, "pretrained_models", "faster-whisper-small")
COSY_PATH = os.path.join(COSY_DIR, "pretrained_models", "Fun-CosyVoice3-0.5B")

logger.info("Загрузка CosyVoice 3 в GPU...")
cosyvoice = AutoModel(model_dir=COSY_PATH)
logger.info("CosyVoice 3 успешно загружен")

generation_lock = threading.Lock()
app = FastAPI(title="TTS & Overlay Studio")

@app.middleware("http")
async def verify_request_origin(request, call_next):
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        origin = request.headers.get("origin")
        host = request.headers.get("host", "")
        if origin and not same_origin(origin, host, request.url.scheme):
            return JSONResponse(status_code=403, content={"detail": "Origin не совпадает с адресом студии."})
    return await call_next(request)

config_store = ConfigStore(SERVER_DIR)
load_config = config_store.load_config
save_config = config_store.save_config
load_da_config = config_store.load_da_config
save_da_config = config_store.save_da_config
load_da_tokens = config_store.load_da_tokens
save_da_tokens = config_store.save_da_tokens
configure_worker(SERVER_DIR, LOG_DIR, load_config, load_da_config, load_da_tokens, save_da_tokens)
from studio.services.tts_engine import PROMPT_CACHE, clear_vram, configure_tts, generate_voice
configure_tts(cosyvoice, generation_lock, load_config, logger)
from studio.services.audio_tools import configure_audio_tools, convert_to_clean_wav
configure_audio_tools(FFMPEG_PATH, TEMP_DIR)

# ==================== WEBSOCKET МЕНЕДЖЕР ====================


da_worker = DonationAlertsWorker()

@app.on_event("startup")
async def app_startup():
    da_worker.start()

# ==================== СТАТИКА И МАРШРУТЫ ====================
DASHBOARD_DIR = os.path.join(BASE_DIR, "web", "dashboard")
OVERLAY_DIR = os.path.join(BASE_DIR, "web", "overlay")

app.mount("/char_files", StaticFiles(directory=CHARACTERS_DIR), name="char_files")
app.mount("/fonts", StaticFiles(directory=FONTS_DIR), name="fonts")
app.mount("/dashboard", StaticFiles(directory=DASHBOARD_DIR, html=True), name="dashboard")
app.mount("/overlay_static", StaticFiles(directory=OVERLAY_DIR), name="overlay_static")
from studio.routes.pages import create_pages_router
app.include_router(create_pages_router(DASHBOARD_DIR, OVERLAY_DIR, ws_manager, same_origin))

DEFAULT_PRESET = {
    "name": "Новый персонаж",
    "reference_text": "",
    "speed": 1.0,
    "theme": {
        "border_color": "#6366f1",
        "bg_color": "#0d0b14",
        "text_color": "#fcebeb",
        "name_bg_color": "#6366f1",
        "name_text_color": "#ffffff",
        "bg_opacity": 0.9,
        "hide_delay": 2.0,
        "avatar_position": "left",
        "box_shape": "shape-rounded",
        "border_fx": "fx-neon",
        "font_family": "Comfortaa",
        "font_size": 22,
        "entrance_animation": "slide-up",
        "exit_animation": "fade-out",
        "text_animation": "typewriter"
    }
}

def load_presets() -> dict:
    try:
        presets = read_json(PRESETS_FILE, {}, strict=True)
    except StorageError as exc:
        logging.getLogger(__name__).error("Не удалось прочитать presets.json или его резервную копию: %s", exc)
        raise HTTPException(status_code=503, detail="Файл персонажей повреждён. Сохранение отключено до восстановления.")
    if not isinstance(presets, dict):
        raise HTTPException(status_code=503, detail="Файл персонажей имеет неверный формат.")
    return presets

def save_presets(data: dict):
    write_json_atomic(PRESETS_FILE, data)

def get_active_character_id() -> str:
    active = read_json(ACTIVE_FILE, {"active": ""}, strict=False)
    if isinstance(active, dict) and isinstance(active.get("active", ""), str) and active.get("active"):
        return active["active"]
    presets = load_presets()
    return list(presets.keys())[0] if presets else ""

def set_active_character_id(char_id: str):
    write_json_atomic(ACTIVE_FILE, {"active": char_id})

# ==================== СИСТЕМНЫЕ НАСТРОЙКИ API ====================
def require_character(char_id):
    if not isinstance(char_id, str) or not re.fullmatch(r"[a-z0-9_-]+", char_id):
        raise HTTPException(status_code=404, detail="Персонаж не найден.")
    if char_id not in load_presets():
        raise HTTPException(status_code=404, detail="Персонаж не найден.")
    return char_id

def validate_host(value):
    if not isinstance(value, str):
        raise HTTPException(status_code=400, detail="Host должен быть строкой.")
    host = value.strip()
    if not is_valid_bind_host(host):
        raise HTTPException(status_code=400, detail="Некорректный host. Укажите IP-адрес или корректное DNS-имя.")
    return host

def validate_streamerbot_url(value):
    parsed = urllib.parse.urlsplit(str(value).strip())
    try:
        valid_port = parsed.port is None or 1 <= parsed.port <= 65535
    except ValueError:
        valid_port = False
    if parsed.scheme not in ("http", "https") or not parsed.hostname or not valid_port or parsed.username or parsed.password:
        raise HTTPException(status_code=400, detail="Некорректный URL Streamer.bot. Допустимы только http/https URL с адресом сервера.")
    return str(value).strip()

from studio.routes.system import create_system_router
app.include_router(create_system_router(load_config, save_config, get_file_lock, CONFIG_FILE, ws_manager, validate_host, validate_port))

# ==================== DONATIONALERTS API ====================
from studio.routes.donations import create_donation_router
app.include_router(create_donation_router(da_worker, load_da_config, save_da_config, load_da_tokens, save_da_tokens, get_file_lock, DA_CONFIG_FILE, DA_TOKENS_FILE, validate_streamerbot_url, logger))
from studio.routes.characters import create_characters_router
app.include_router(create_characters_router(load_presets, save_presets, get_active_character_id, set_active_character_id, DEFAULT_PRESET, require_character, CHARACTERS_DIR, PRESETS_FILE, ACTIVE_FILE, get_file_lock, write_bytes_atomic, convert_to_clean_wav, PROMPT_CACHE, logger))
from studio.routes.fonts import create_fonts_router
app.include_router(create_fonts_router(CUSTOM_FONTS_DIR, write_bytes_atomic))
from studio.routes.tools import create_tools_router
app.include_router(create_tools_router(TEMP_DIR, WHISPER_PATH, FFMPEG_PATH, np, sf, torch, torchaudio, WhisperModel, generation_lock, convert_to_clean_wav, clear_vram, generate_voice, has_speakable_content, sanitize_overlay_text, ws_manager, require_character, CHARACTERS_DIR, get_active_character_id, logger))
from studio.routes.speak import create_speak_router
app.include_router(create_speak_router(load_presets, get_active_character_id, CHARACTERS_DIR, generate_voice, ws_manager, has_speakable_content, sanitize_overlay_text, torch, logger))

# ==================== ОСТАЛЬНЫЕ МАРШРУТЫ СТУДИИ ====================
if __name__ == "__main__":
    import uvicorn
    cfg = load_config()
    host = cfg.get("host", "127.0.0.1")
    port = int(cfg.get("port", 8765))
    
    if cfg.get("auto_open_browser", True):
        browser_host = "127.0.0.1" if host == "0.0.0.0" else ("[{}]".format(host) if ":" in host and not host.startswith("[") else host)
        threading.Timer(1.0, lambda: webbrowser.open(f"http://{browser_host}:{port}/dashboard")).start()
        
    uvicorn.run(app, host=host, port=port, log_level="info")
