# -*- coding: utf-8 -*-
import os
import sys
import ctypes
import asyncio
import subprocess
import time

SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from studio.core.env import configure_environment
ENV = configure_environment(SERVER_DIR)
BASE_DIR = ENV["BASE_DIR"]
COSY_DIR = ENV["COSY_DIR"]
CHARACTERS_DIR = ENV["CHARACTERS_DIR"]
PRESETS_FILE = ENV["PRESETS_FILE"]
ACTIVE_FILE = ENV["ACTIVE_FILE"]
CONFIG_FILE = ENV["CONFIG_FILE"]
DA_CONFIG_FILE = ENV["DA_CONFIG_FILE"]
DA_TOKENS_FILE = ENV["DA_TOKENS_FILE"]
TEMP_DIR = ENV["TEMP_DIR"]
FFMPEG_PATH = ENV["FFMPEG_PATH"]
FONTS_DIR = ENV["FONTS_DIR"]
BUNDLED_FONTS_DIR = ENV["BUNDLED_FONTS_DIR"]
CUSTOM_FONTS_DIR = ENV["CUSTOM_FONTS_DIR"]
AUDIO_TOOLS_CACHE = ENV["AUDIO_TOOLS_CACHE"]
LOG_DIR = ENV["LOG_DIR"]
DASHBOARD_DIR = ENV["DASHBOARD_DIR"]
OVERLAY_DIR = ENV["OVERLAY_DIR"]
logger = ENV["logger"]

_INSTANCE_MUTEX = None
if os.name == "nt":
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_mutex = kernel32.CreateMutexW
    create_mutex.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    create_mutex.restype = ctypes.c_void_p
    ctypes.set_last_error(0)
    _INSTANCE_MUTEX = create_mutex(None, False, "Local\\StreamTTSStudio")
    mutex_error = ctypes.get_last_error()
    if not _INSTANCE_MUTEX:
        raise OSError(mutex_error, "Не удалось создать mutex экземпляра студии")
    if mutex_error == 183:
        logger.error("Студия уже запущена. Второй экземпляр не будет загружать модель.")
        if os.environ.get("STUDIO_MONITOR_MODE") == "1":
            ctypes.windll.user32.MessageBoxW(None, "Студия уже запущена. Используйте существующее окно мониторинга.", "TTS Studio", 0x40)
        sys.exit(1)

from studio.core.monitor import MonitorLogHandler, set_shutdown_callback
logger.addHandler(MonitorLogHandler())

import re
import threading
import webbrowser
import logging
import urllib.parse

import numpy as np
import torch
import torchaudio
import soundfile as sf
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from faster_whisper import WhisperModel

from studio.core.storage import StorageError, get_file_lock, read_json, write_json_atomic, write_bytes_atomic
from studio.core.config import ConfigStore
from studio.core.ws import ws_manager
from studio.services.text import has_speakable_content, sanitize_overlay_text
from studio.core.validation import is_valid_bind_host, same_origin, validate_port, validate_http_url
from studio.services.da_worker import DonationAlertsWorker, configure_worker
from studio.services.tts_engine import load_cosyvoice_model

# Подавляем назойливые DEBUG логи multipart и websockets в консоли
logging.getLogger("multipart").setLevel(logging.WARNING)
logging.getLogger("websockets").setLevel(logging.WARNING)

class EndpointFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return "GET /api/system_config" not in msg and "GET /api/da/config" not in msg

logging.getLogger("uvicorn.access").addFilter(EndpointFilter())

logger.info("=" * 60)
logger.info("TTS STUDIO & OVERLAY BACKEND (CosyVoice 3 + Whisper + Demucs + DA)")
logger.info("=" * 60)

WHISPER_PATH = os.path.join(COSY_DIR, "pretrained_models", "faster-whisper-small")
COSY_PATH = os.path.join(COSY_DIR, "pretrained_models", "Fun-CosyVoice3-0.5B")

logger.info("Загрузка CosyVoice 3 в GPU...")
cosyvoice = load_cosyvoice_model(COSY_PATH)
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
configure_tts(cosyvoice, generation_lock, load_config, logger, np, torch)
from studio.services.audio_tools import configure_audio_tools, convert_to_clean_wav
configure_audio_tools(FFMPEG_PATH, TEMP_DIR)

# ==================== WEBSOCKET МЕНЕДЖЕР ====================


da_worker = DonationAlertsWorker()

@app.on_event("startup")
async def app_startup():
    da_worker.start()

@app.on_event("shutdown")
async def app_shutdown():
    task = da_worker.task
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

# ==================== СТАТИКА И МАРШРУТЫ ====================
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
    try:
        return validate_http_url(value)
    except ValueError:
        raise HTTPException(status_code=400, detail="Некорректный URL Streamer.bot. Допустимы только http/https URL с адресом сервера.")

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
    monitor_mode = os.environ.get("STUDIO_MONITOR_MODE") == "1"
    browser_host = "127.0.0.1" if host == "0.0.0.0" else ("[{}]".format(host) if ":" in host and not host.startswith("[") else host)
    base_url = f"http://{browser_host}:{port}"
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="info", timeout_graceful_shutdown=300))
    set_shutdown_callback(lambda: setattr(server, "should_exit", True))

    def open_window_when_ready():
        deadline = time.time() + 180
        while not server.started and not server.should_exit and time.time() < deadline:
            time.sleep(0.25)
        if not server.started:
            return
        if monitor_mode:
            monitor_url = base_url + "/monitor"
            edge_candidates = [
                os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
                os.path.join(os.environ.get("PROGRAMFILES", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
                os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
            ]
            edge_path = next((path for path in edge_candidates if path and os.path.isfile(path)), None)
            if edge_path:
                try:
                    subprocess.Popen([edge_path, "--app=" + monitor_url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except Exception:
                    webbrowser.open(monitor_url)
            else:
                webbrowser.open(monitor_url)
        elif cfg.get("auto_open_browser", True):
            webbrowser.open(base_url + "/dashboard")

    if monitor_mode or cfg.get("auto_open_browser", True):
        threading.Thread(target=open_window_when_ready, daemon=True).start()
    server.run()
