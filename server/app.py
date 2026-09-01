# -*- coding: utf-8 -*-
import os
import sys
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
from typing import Optional, List

import requests
import websockets

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
OUTPUT_DIR = os.path.join(BASE_DIR, "output", "tts_output")
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
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(BUNDLED_FONTS_DIR, exist_ok=True)
os.makedirs(CUSTOM_FONTS_DIR, exist_ok=True)
os.makedirs(AUDIO_TOOLS_CACHE, exist_ok=True)

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
from fastapi.responses import Response, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from faster_whisper import WhisperModel
from cosyvoice.cli.cosyvoice import AutoModel

print("=" * 60)
print("  TTS STUDIO & OVERLAY BACKEND (CosyVoice 3 + Whisper + Demucs + DA)")
print("=" * 60)

WHISPER_PATH = os.path.join(COSY_DIR, "pretrained_models", "faster-whisper-small")
COSY_PATH = os.path.join(COSY_DIR, "pretrained_models", "Fun-CosyVoice3-0.5B")

print("[1/1] Загрузка CosyVoice 3 в GPU...")
cosyvoice = AutoModel(model_dir=COSY_PATH)
print("CosyVoice 3 успешно загружен!\n")

generation_lock = threading.Lock()
app = FastAPI(title="TTS & Overlay Studio")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PROMPT_CACHE = {}

DEFAULT_CONFIG = {
    "host": "127.0.0.1",
    "port": 8765,
    "n_timesteps": 6,
    "auto_open_browser": True
}

def load_config() -> dict:
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            return {**DEFAULT_CONFIG, **cfg}
    except Exception:
        return DEFAULT_CONFIG.copy()

def save_config(cfg: dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

# ==================== DONATIONALERTS ХРАНИЛИЩЕ ====================
DEFAULT_DA_CONFIG = {
    "enabled": False,
    "client_id": "",
    "client_secret": "",
    "streamerbot_url": "http://127.0.0.1:7474/DoAction",
    "streamerbot_action": "Donation"
}

def load_da_config() -> dict:
    if not os.path.exists(DA_CONFIG_FILE):
        save_da_config(DEFAULT_DA_CONFIG)
        return DEFAULT_DA_CONFIG.copy()
    try:
        with open(DA_CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            return {**DEFAULT_DA_CONFIG, **cfg}
    except Exception:
        return DEFAULT_DA_CONFIG.copy()

def save_da_config(cfg: dict):
    with open(DA_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

def load_da_tokens() -> Optional[dict]:
    if not os.path.exists(DA_TOKENS_FILE):
        return None
    try:
        with open(DA_TOKENS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def save_da_tokens(tokens: dict):
    with open(DA_TOKENS_FILE, "w", encoding="utf-8") as f:
        json.dump(tokens, f, ensure_ascii=False, indent=2)

# ==================== WEBSOCKET МЕНЕДЖЕР ====================
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self._loop = None

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        self._loop = asyncio.get_event_loop()

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)

    def broadcast_sync(self, message: dict):
        if self._loop and self.active_connections:
            asyncio.run_coroutine_threadsafe(self.broadcast(message), self._loop)

ws_manager = ConnectionManager()

# ==================== DONATIONALERTS ASYNC РАБОТНИК ====================
DA_AUTH_URL = "https://www.donationalerts.com/oauth/authorize"
DA_TOKEN_URL = "https://www.donationalerts.com/oauth/token"
DA_USER_API_URL = "https://www.donationalerts.com/api/v1/user/oauth"
DA_SUBSCRIBE_API_URL = "https://www.donationalerts.com/api/v1/centrifuge/subscribe"
DA_CENTRIFUGO_WS_URL = "wss://centrifugo.donationalerts.com/connection/websocket"
DA_SCOPES = "oauth-donation-subscribe oauth-user-show"

class DonationAlertsWorker:
    def __init__(self):
        self.task: Optional[asyncio.Task] = None
        self.is_connected = False
        self.authorized_user = ""
        self.last_error = ""

    def get_redirect_uri(self) -> str:
        cfg = load_config()
        port = cfg.get("port", 8765)
        return f"http://127.0.0.1:{port}/api/da/callback"

    def refresh_tokens(self, refresh_token: str, client_id: str, client_secret: str) -> Optional[dict]:
        payload = {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "scope": DA_SCOPES
        }
        try:
            resp = requests.post(DA_TOKEN_URL, data=payload, timeout=10)
            if resp.status_code == 200:
                tokens = resp.json()
                save_da_tokens(tokens)
                return tokens
        except Exception:
            pass
        return None

    def get_access_token(self) -> Optional[str]:
        tokens = load_da_tokens()
        da_cfg = load_da_config()
        if not tokens or not da_cfg.get("client_id") or not da_cfg.get("client_secret"):
            return None

        headers = {"Authorization": f"Bearer {tokens.get('access_token')}"}
        try:
            resp = requests.get(DA_USER_API_URL, headers=headers, timeout=8)
            if resp.status_code == 200:
                profile = resp.json().get("data", {})
                self.authorized_user = profile.get("name", "")
                return tokens.get("access_token")

            if resp.status_code == 401 and "refresh_token" in tokens:
                refreshed = self.refresh_tokens(tokens["refresh_token"], da_cfg["client_id"], da_cfg["client_secret"])
                if refreshed:
                    return refreshed.get("access_token")
        except Exception as e:
            self.last_error = str(e)
        return None

    def send_to_streamerbot(self, donor: str, amount: float, currency: str, message: str):
        da_cfg = load_da_config()
        sb_url = da_cfg.get("streamerbot_url", "http://127.0.0.1:7474/DoAction")
        sb_action = da_cfg.get("streamerbot_action", "Donation").strip()

        payload = {
            "action": {"name": sb_action} if not sb_action.startswith("{") else json.loads(sb_action),
            "args": {
                "user": str(donor),
                "donorName": str(donor),
                "amount": float(amount),
                "currency": str(currency),
                "message": str(message),
                "rawInput": str(message)
            }
        }
        try:
            r = requests.post(sb_url, json=payload, timeout=4)
            print(f"[DA Listener -> Streamer.bot] {donor}: {amount} {currency} | Ответ SB: {r.status_code}")
        except Exception as e:
            print(f"[DA Listener] Ошибка передачи в Streamer.bot ({sb_url}): {e}")

    async def run_loop(self):
        while True:
            da_cfg = load_da_config()
            if not da_cfg.get("enabled", False):
                self.is_connected = False
                await asyncio.sleep(3)
                continue

            access_token = self.get_access_token()
            if not access_token:
                self.is_connected = False
                self.last_error = "Требуется авторизация OAuth"
                await asyncio.sleep(5)
                continue

            try:
                headers = {"Authorization": f"Bearer {access_token}"}
                profile_resp = requests.get(DA_USER_API_URL, headers=headers, timeout=10)
                if profile_resp.status_code != 200:
                    raise RuntimeError("Не удалось получить профиль пользователя DA")

                profile = profile_resp.json()["data"]
                user_id = profile["id"]
                self.authorized_user = profile.get("name", "")
                socket_token = profile.get("socket_connection_token")
                channel = f"$alerts:donation_{user_id}"

                async with websockets.connect(DA_CENTRIFUGO_WS_URL, ping_interval=20, ping_timeout=10) as ws:
                    await ws.send(json.dumps({"params": {"token": socket_token}, "id": 1}))
                    connect_res = json.loads(await ws.recv())
                    client_id = connect_res.get("result", {}).get("client")
                    if not client_id:
                        raise RuntimeError(f"Ошибка авторизации Centrifugo: {connect_res}")

                    sub_token_resp = requests.post(
                        DA_SUBSCRIBE_API_URL,
                        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                        json={"channels": [channel], "client": client_id},
                        timeout=10
                    )
                    sub_token = None
                    for ch in sub_token_resp.json().get("channels", []):
                        if ch.get("channel") == channel:
                            sub_token = ch.get("token")
                            break

                    if not sub_token:
                        raise RuntimeError("Не удалось получить токен подписки на канал алертов")

                    await ws.send(json.dumps({"params": {"channel": channel, "token": sub_token}, "method": 1, "id": 2}))
                    sub_res = json.loads(await ws.recv())
                    if "error" in sub_res:
                        raise RuntimeError(f"Ошибка подписки: {sub_res['error']}")

                    self.is_connected = True
                    self.last_error = ""
                    print(f"[DA Listener] Подключено к DA Centrifugo (Аккаунт: {self.authorized_user})")

                    try:
                        while True:
                            da_cfg_current = load_da_config()
                            if not da_cfg_current.get("enabled", False):
                                break

                            raw_msg = await ws.recv()
                            if not raw_msg or not raw_msg.strip():
                                continue

                            for line in raw_msg.strip().split("\n"):
                                line = line.strip()
                                if not line or line == "{}":
                                    continue

                                try:
                                    data = json.loads(line)
                                except Exception:
                                    continue

                                payload_data = None
                                if "result" in data and "data" in data["result"]:
                                    payload_data = data["result"]["data"].get("data")
                                elif "push" in data and "pub" in data["push"]:
                                    payload_data = data["push"]["pub"].get("data")

                                if payload_data:
                                    if isinstance(payload_data, str):
                                        try:
                                            payload_data = json.loads(payload_data)
                                        except Exception:
                                            pass

                                    donor = payload_data.get("username") or payload_data.get("user") or "Добрый человек"
                                    amount = payload_data.get("amount") or payload_data.get("sum") or 0
                                    currency = payload_data.get("currency") or "RUB"
                                    message = payload_data.get("message") or payload_data.get("comment") or ""

                                    print(f"\n[DA Донат] {donor}: {amount} {currency} | Текст: {message}")
                                    self.send_to_streamerbot(donor, amount, currency, message)

                    except asyncio.CancelledError:
                        raise

            except Exception as e:
                self.is_connected = False
                self.last_error = str(e)
                print(f"[DA Listener] Переподключение к сокету через 5с... (Причина: {e})")
                await asyncio.sleep(5)

    def start(self):
        if not self.task or self.task.done():
            self.task = asyncio.create_task(self.run_loop())

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

@app.get("/")
def root():
    return FileResponse(os.path.join(DASHBOARD_DIR, "index.html"))

@app.get("/favicon.ico")
def get_favicon():
    fav_path = os.path.join(DASHBOARD_DIR, "favicon.ico")
    if os.path.exists(fav_path):
        return FileResponse(fav_path)
    return Response(status_code=204)

@app.get("/overlay")
@app.get("/overlay/")
def get_overlay_page():
    return FileResponse(os.path.join(OVERLAY_DIR, "overlay.html"))

@app.websocket("/ws/overlay")
async def websocket_overlay(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)

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
    if not os.path.exists(PRESETS_FILE):
        return {}
    try:
        with open(PRESETS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_presets(data: dict):
    with open(PRESETS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_active_character_id() -> str:
    if os.path.exists(ACTIVE_FILE):
        try:
            with open(ACTIVE_FILE, "r", encoding="utf-8") as f:
                return json.load(f).get("active", "")
        except Exception:
            pass
    presets = load_presets()
    return list(presets.keys())[0] if presets else ""

def set_active_character_id(char_id: str):
    with open(ACTIVE_FILE, "w", encoding="utf-8") as f:
        json.dump({"active": char_id}, f, ensure_ascii=False, indent=2)

def clear_vram():
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    gc.collect()

def num_to_ru_words(n: int) -> str:
    if n == 0:
        return "ноль"
    if n < 0:
        return "минус " + num_to_ru_words(abs(n))

    units_m = ["", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять"]
    units_f = ["", "одна", "две", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять"]
    teens = ["десять", "одиннадцать", "двенадцать", "тринадцать", "четырнадцать", 
             "пятнадцать", "шестнадцать", "семнадцать", "восемнадцать", "девятнадцать"]
    tens = ["", "", "двадцать", "тридцать", "сорок", "пятьдесят", "шестьдесят", "семьдесят", "восемьдесят", "девяносто"]
    hundreds = ["", "сто", "двести", "триста", "четыреста", "пятьсот", "шестьсот", "семьсот", "восемьсот", "девятьсот"]

    def triplet(val: int, is_female: bool = False) -> str:
        res = []
        h = val // 100
        t = (val % 100) // 10
        u = val % 10
        if h > 0:
            res.append(hundreds[h])
        if t == 1:
            res.append(teens[u])
        else:
            if t > 1:
                res.append(tens[t])
            if u > 0:
                res.append(units_f[u] if is_female else units_m[u])
        return " ".join(res)

    def plural_form(val: int, f1: str, f2: str, f5: str) -> str:
        n100 = val % 100
        n10 = val % 10
        if 11 <= n100 <= 19:
            return f5
        if n10 == 1:
            return f1
        if 2 <= n10 <= 4:
            return f2
        return f5

    parts = []
    millions = n // 1000000
    if millions > 0:
        parts.append(triplet(millions, is_female=False))
        parts.append(plural_form(millions, "миллион", "миллиона", "миллионов"))
        n %= 1000000

    thousands = n // 1000
    if thousands > 0:
        parts.append(triplet(thousands, is_female=True))
        parts.append(plural_form(thousands, "тысяча", "тысячи", "тысяч"))
        n %= 1000

    if n > 0 or not parts:
        parts.append(triplet(n, is_female=False))

    return " ".join([p for p in parts if p]).strip()

def sanitize_text(text: str) -> str:
    text = re.sub(r'https?://\S+|www\.\S+', 'ссылка', text)
    text = re.sub(r'[\U00010000-\U0010ffff]', '', text)
    
    def replace_isolated_digits(match):
        val_str = match.group(0)
        try:
            val = int(val_str)
            return num_to_ru_words(val)
        except ValueError:
            return val_str

    text = re.sub(r'(?<![A-Za-z0-9_])\d+(?![A-Za-z0-9_])', replace_isolated_digits, text)
    text = re.sub(r'([.!?])\1{2,}', r'\1\1', text)
    return text.strip()

def clean_and_smooth_chunk(audio: np.ndarray, sr: int = 24000) -> np.ndarray:
    if len(audio) == 0:
        return audio
    audio = audio - np.mean(audio)
    trim_start = int(sr * 0.008)
    trim_end = int(sr * 0.025)
    if len(audio) > (trim_start + trim_end + 1000):
        audio = audio[trim_start:-trim_end]
    fade_len = int(sr * 0.015)
    if len(audio) > fade_len * 2:
        fade_in = 0.5 * (1 - np.cos(np.linspace(0, np.pi, fade_len)))
        fade_out = 0.5 * (1 + np.cos(np.linspace(0, np.pi, fade_len)))
        audio[:fade_len] *= fade_in
        audio[-fade_len:] *= fade_out
    return audio

def numpy_to_wav(audio: np.ndarray, sample_rate: int) -> bytes:
    audio = np.asarray(audio, dtype=np.float32)
    audio = np.clip(audio, -1.0, 1.0)
    pcm = (audio * 32767).astype(np.int16)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm.tobytes())
    return buffer.getvalue()

def generate_voice(raw_text: str, voice_wav_path: str, ref_text: str, speed: float = 1.0) -> tuple[bytes, float]:
    global PROMPT_CACHE
    cfg = load_config()
    n_timesteps = int(cfg.get("n_timesteps", 6))

    with generation_lock:
        start_time = time.time()
        clean_text = sanitize_text(raw_text)
        sentences = [s.strip() for s in re.split(r'(?<=[.!?…\n])\s+', clean_text) if s.strip()]
        if not sentences:
            sentences = [clean_text]

        print(f"\n[TTS] Старт генерации ({len(sentences)} предл., {n_timesteps} steps): \"{clean_text}\"")

        with torch.inference_mode():
            prompt_text = "You are a helpful assistant.<|endofprompt|>" + ref_text
            
            cache_key = f"{voice_wav_path}_{prompt_text}"
            if cache_key in PROMPT_CACHE:
                prompt_text_norm = PROMPT_CACHE[cache_key]
            else:
                prompt_text_norm = cosyvoice.frontend.text_normalize(prompt_text, split=False, text_frontend=True)
                PROMPT_CACHE[cache_key] = prompt_text_norm

            sr = cosyvoice.sample_rate
            audio_chunks = []
            silence_gap = np.zeros(int(sr * 0.08), dtype=np.float32)

            for idx, sentence in enumerate(sentences):
                if not sentence.endswith(('.', '!', '?', '…')):
                    sentence += '.'
                text_normalized = cosyvoice.frontend.text_normalize(sentence, split=False, text_frontend=True)
                
                model_input = cosyvoice.frontend.frontend_zero_shot(
                    text_normalized, prompt_text_norm, voice_wav_path, sr, ""
                )

                chunk_parts = []
                for result in cosyvoice.model.tts(**model_input, stream=False, speed=speed, n_timesteps=n_timesteps):
                    audio = result["tts_speech"]
                    if hasattr(audio, "detach"):
                        audio = audio.detach().cpu().numpy()
                    audio = np.asarray(audio, dtype=np.float32).flatten()
                    if len(audio) > 0:
                        chunk_parts.append(audio)

                if chunk_parts:
                    single_chunk = np.concatenate(chunk_parts)
                    single_chunk = clean_and_smooth_chunk(single_chunk, sr)
                    audio_chunks.append(single_chunk)
                    if idx < len(sentences) - 1:
                        audio_chunks.append(silence_gap)

            if not audio_chunks:
                raise RuntimeError("CosyVoice не вернул аудио.")

            final_audio = np.concatenate(audio_chunks)
            clear_vram()

            elapsed = round(time.time() - start_time, 2)
            duration = round(len(final_audio) / sr, 2)
            print(f"[TTS] Успешно! Синтез: {elapsed}с | Длительность аудио: {duration}с\n")

            return numpy_to_wav(final_audio, sr), duration

# ==================== СИСТЕМНЫЕ НАСТРОЙКИ API ====================
@app.get("/api/system_config")
def api_get_system_config():
    cfg = load_config()
    return {
        "config": cfg,
        "obs_connected": len(ws_manager.active_connections) > 0,
        "active_connections_count": len(ws_manager.active_connections)
    }

@app.post("/api/system_config")
def api_save_system_config(data: dict):
    cfg = load_config()
    if "host" in data: cfg["host"] = str(data["host"]).strip()
    if "port" in data: cfg["port"] = int(data["port"])
    if "n_timesteps" in data: cfg["n_timesteps"] = max(4, min(15, int(data["n_timesteps"])))
    if "auto_open_browser" in data: cfg["auto_open_browser"] = bool(data["auto_open_browser"])
    save_config(cfg)
    return {"status": "ok", "config": cfg}

# ==================== DONATIONALERTS API ====================
@app.get("/api/da/config")
def api_get_da_config():
    da_cfg = load_da_config()
    tokens = load_da_tokens()
    return {
        "config": da_cfg,
        "has_tokens": tokens is not None,
        "redirect_uri": da_worker.get_redirect_uri(),
        "authorized_user": da_worker.authorized_user,
        "is_connected": da_worker.is_connected,
        "last_error": da_worker.last_error
    }

@app.post("/api/da/config")
def api_save_da_config(data: dict):
    da_cfg = load_da_config()
    if "enabled" in data: da_cfg["enabled"] = bool(data["enabled"])
    if "client_id" in data: da_cfg["client_id"] = str(data["client_id"]).strip()
    if "client_secret" in data: da_cfg["client_secret"] = str(data["client_secret"]).strip()
    if "streamerbot_url" in data: da_cfg["streamerbot_url"] = str(data["streamerbot_url"]).strip()
    if "streamerbot_action" in data: da_cfg["streamerbot_action"] = str(data["streamerbot_action"]).strip()
    save_da_config(da_cfg)
    return {"status": "ok", "config": da_cfg}

@app.get("/api/da/auth_url")
def api_get_da_auth_url():
    da_cfg = load_da_config()
    client_id = da_cfg.get("client_id", "").strip()
    if not client_id:
        raise HTTPException(status_code=400, detail="Сначала укажите ID приложения в настройках!")

    redirect_uri = da_worker.get_redirect_uri()
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": DA_SCOPES
    }
    return {"auth_url": f"{DA_AUTH_URL}?{urllib.parse.urlencode(params)}"}

@app.get("/api/da/callback")
def api_da_callback(code: Optional[str] = None, error: Optional[str] = None):
    if error:
        return HTMLResponse(f"<h3>Ошибка авторизации DonationAlerts: {error}</h3><p>Можете закрыть это окно.</p>")
    if not code:
        return HTMLResponse("<h3>Код авторизации не получен!</h3>")

    da_cfg = load_da_config()
    client_id = da_cfg.get("client_id", "").strip()
    client_secret = da_cfg.get("client_secret", "").strip()
    redirect_uri = da_worker.get_redirect_uri()

    payload = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "code": code
    }
    try:
        resp = requests.post(DA_TOKEN_URL, data=payload, timeout=10)
        if resp.status_code != 200:
            return HTMLResponse(f"<h3>Ошибка получения токена ({resp.status_code}): {resp.text}</h3>")

        tokens = resp.json()
        save_da_tokens(tokens)
        da_cfg["enabled"] = True
        save_da_config(da_cfg)

        return HTMLResponse("""
            <html>
                <body style="background:#0b0a10; color:#10b981; font-family:sans-serif; text-align:center; padding:50px;">
                    <h2>✓ Успешная авторизация в DonationAlerts!</h2>
                    <p style="color:#eae8f0;">Токены сохранены. Слушатель активирован. Вы можете закрыть эту вкладку и вернуться в студию.</p>
                    <script>setTimeout(() => window.close(), 3000);</script>
                </body>
            </html>
        """)
    except Exception as e:
        return HTMLResponse(f"<h3>Исключение: {str(e)}</h3>")

@app.post("/api/da/test_donation")
def api_test_da_donation(data: dict):
    donor = str(data.get("user", "Тестовый Донатер"))
    amount = float(data.get("amount", 250))
    currency = str(data.get("currency", "RUB"))
    message = str(data.get("message", "Это тестовый донат из панели управления студии!"))

    da_worker.send_to_streamerbot(donor, amount, currency, message)
    return {"status": "ok", "sent": {"donor": donor, "amount": amount, "currency": currency, "message": message}}

# ==================== ОСТАЛЬНЫЕ МАРШРУТЫ СТУДИИ ====================
@app.get("/api/presets")
def get_presets_list():
    presets = load_presets()
    active = get_active_character_id()
    
    for char_id, data in presets.items():
        avatar_path = os.path.join(CHARACTERS_DIR, char_id, "avatar.png")
        has_avatar = os.path.exists(avatar_path)
        data["has_avatar"] = has_avatar
        data["avatar_url"] = f"/char_files/{char_id}/avatar.png" if has_avatar else ""
        
    return {"presets": presets, "active": active}

@app.post("/api/presets/set_active")
def api_set_active(data: dict):
    char_id = data.get("id")
    presets = load_presets()
    if char_id not in presets:
        raise HTTPException(status_code=404, detail="Персонаж не найден.")
    set_active_character_id(char_id)
    return {"status": "ok", "active": char_id}

@app.get("/api/active_overlay_config")
def get_active_overlay_config(char_id: Optional[str] = None):
    presets = load_presets()
    target_id = char_id or get_active_character_id()
    char_data = presets.get(target_id, DEFAULT_PRESET)
    
    avatar_url = ""
    if target_id:
        avatar_path = os.path.join(CHARACTERS_DIR, target_id, "avatar.png")
        if os.path.exists(avatar_path):
            avatar_url = f"/char_files/{target_id}/avatar.png"
            
    return {
        "id": target_id,
        "name": char_data.get("name", "Персонаж"),
        "avatar": avatar_url,
        "theme": char_data.get("theme", DEFAULT_PRESET["theme"])
    }

@app.get("/api/fonts")
def api_get_fonts():
    custom_list = []
    if os.path.exists(CUSTOM_FONTS_DIR):
        for f in sorted(os.listdir(CUSTOM_FONTS_DIR)):
            if f.lower().endswith(('.ttf', '.otf', '.woff2', '.woff')):
                font_name = os.path.splitext(f)[0]
                custom_list.append({
                    "name": font_name,
                    "file": f,
                    "url": f"/fonts/custom/{f}"
                })
    return {"custom_fonts": custom_list}

@app.post("/api/upload_font")
async def api_upload_font(file: UploadFile = File(...)):
    filename = file.filename or ""
    raw_name, ext = os.path.splitext(filename)
    ext = ext.lower()
    allowed_exts = ['.ttf', '.otf', '.woff2', '.woff']
    if ext not in allowed_exts:
        raise HTTPException(status_code=400, detail=f"Поддерживаются только форматы: {', '.join(allowed_exts)}")

    clean_base = re.sub(r'[^a-zA-Z0-9_\-\s]', '', raw_name).strip()
    if not clean_base:
        clean_base = f"font_{int(time.time())}"

    final_filename = f"{clean_base}{ext}"
    dest_path = os.path.join(CUSTOM_FONTS_DIR, final_filename)

    if not os.path.exists(dest_path):
        with open(dest_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        is_duplicate = False
    else:
        is_duplicate = True

    return {
        "status": "ok",
        "name": clean_base,
        "file": final_filename,
        "url": f"/fonts/custom/{final_filename}",
        "is_duplicate": is_duplicate
    }

@app.post("/api/trim_and_transcribe")
async def api_trim_and_transcribe(
    audio: UploadFile = File(...),
    start: float = Form(0.0),
    end: float = Form(0.0)
):
    temp_in = os.path.join(TEMP_DIR, f"trim_in_{int(time.time()*1000)}.wav")
    temp_out = os.path.join(TEMP_DIR, f"trim_out_{int(time.time()*1000)}.wav")
    whisper_model = None
    try:
        with open(temp_in, "wb") as f:
            f.write(await audio.read())

        data, sr = sf.read(temp_in, dtype='float32')
        if data.ndim > 1:
            data = data[:, 0]

        start_frame = max(0, int(start * sr))
        end_frame = min(len(data), int(end * sr)) if end > 0 else len(data)
        
        trimmed_data = data[start_frame:end_frame]
        
        sf.write(temp_out, trimmed_data, sr, format="WAV", subtype="PCM_16")

        device = "cuda" if torch.cuda.is_available() else "cpu"
        whisper_model = WhisperModel(
            WHISPER_PATH, 
            device=device, 
            compute_type="float16" if device == "cuda" else "int8"
        )
        segments, info = whisper_model.transcribe(
            temp_out,
            language=None,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
            condition_on_previous_text=False,
            temperature=0.0,
            beam_size=1
        )
        text = " ".join([s.text.strip() for s in segments]).strip()
        print(f"[Trim+Whisper] Язык: {info.language} ({round(info.language_probability * 100, 1)}%) | Текст: \"{text}\"")

        with open(temp_out, "rb") as f:
            wav_bytes = f.read()

        return {
            "text": text,
            "audio_base64": base64.b64encode(wav_bytes).decode('utf-8')
        }
    except Exception as e:
        print(f"[Whisper Error] {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка обработки: {str(e)}")
    finally:
        if whisper_model is not None:
            del whisper_model
            clear_vram()

        for p in [temp_in, temp_out]:
            if os.path.exists(p):
                try: os.remove(p)
                except Exception: pass

@app.post("/api/normalize_audio")
async def api_normalize_audio(
    audio: UploadFile = File(...),
    target_gain: float = Form(0.95)
):
    try:
        raw_bytes = await audio.read()
        in_bio = io.BytesIO(raw_bytes)
        data, sr = sf.read(in_bio, dtype='float32')
        
        if data.ndim > 1:
            data = data[:, 0]
            
        data = data - np.mean(data)
        peak = np.max(np.abs(data))
        
        if peak > 0.0001:
            gain = target_gain / peak
            data = data * gain
            data = np.clip(data, -0.99, 0.99)

        out_bio = io.BytesIO()
        sf.write(out_bio, data, sr, format="WAV", subtype="PCM_16")
        return Response(content=out_bio.getvalue(), media_type="audio/wav")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка нормализации: {str(e)}")
    finally:
        clear_vram()

@app.post("/api/isolate_vocal")
async def api_isolate_vocal(
    audio: UploadFile = File(...),
    shifts: int = Form(2)
):
    print(f"[Demucs] Старт очистки вокала | Качество (shifts): {shifts}x")
    try:
        raw_bytes = await audio.read()
        in_bio = io.BytesIO(raw_bytes)
        
        from demucs.pretrained import get_model
        from demucs.apply import apply_model

        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = get_model("htdemucs")
        model.to(device)
        model.eval()

        wav, orig_sr = torchaudio.load(in_bio)
        if wav.shape[0] == 1:
            wav_stereo = wav.repeat(2, 1)
        else:
            wav_stereo = wav[:2, :]

        if orig_sr != model.samplerate:
            resample_to_model = torchaudio.transforms.Resample(orig_sr, model.samplerate)
            wav_input = resample_to_model(wav_stereo)
        else:
            wav_input = wav_stereo

        wav_input = wav_input.to(device)

        with torch.no_grad():
            sources = apply_model(model, wav_input[None], device=device, shifts=shifts, split=True, progress=False)[0]

        vocal_idx = model.sources.index("vocals")
        vocals = sources[vocal_idx]
        vocal_mono = vocals[0:1, :]

        if orig_sr != model.samplerate:
            resample_back = torchaudio.transforms.Resample(model.samplerate, orig_sr).to(device)
            vocal_mono = resample_back(vocal_mono)

        vocal_np = vocal_mono.squeeze(0).cpu().numpy()

        out_bio = io.BytesIO()
        sf.write(out_bio, vocal_np, orig_sr, format="WAV", subtype="PCM_16")

        del model, wav, wav_stereo, wav_input, sources, vocals, vocal_mono
        return Response(content=out_bio.getvalue(), media_type="audio/wav")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка очистки голоса: {str(e)}")
    finally:
        clear_vram()

@app.post("/api/convert_to_telegram_ogg")
async def api_convert_to_telegram_ogg(audio: UploadFile = File(...)):
    if not os.path.isfile(FFMPEG_PATH):
        raise HTTPException(status_code=500, detail=f"FFmpeg не найден: {FFMPEG_PATH}")

    temp_wav = os.path.join(TEMP_DIR, f"conv_{int(time.time()*1000)}.wav")
    temp_ogg = os.path.join(TEMP_DIR, f"conv_{int(time.time()*1000)}.ogg")

    try:
        with open(temp_wav, "wb") as f:
            f.write(await audio.read())

        cmd = [
            FFMPEG_PATH, "-y", "-i", temp_wav,
            "-c:a", "libopus", "-b:a", "32k", "-vbr", "on",
            "-compression_level", "10", "-frame_duration", "60",
            "-application", "voip", "-ar", "48000", "-ac", "1",
            temp_ogg
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg error: {res.stderr[-200:]}")

        with open(temp_ogg, "rb") as f:
            ogg_bytes = f.read()

        return Response(content=ogg_bytes, media_type="audio/ogg")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка конвертации: {str(e)}")
    finally:
        for p in [temp_wav, temp_ogg]:
            if os.path.exists(p):
                try: os.remove(p)
                except Exception: pass
        clear_vram()

@app.post("/api/test_draft_tts")
async def api_test_draft_tts(
    text: str = Form(...),
    ref_text: str = Form(...),
    speed: float = Form(1.0),
    char_id: Optional[str] = Form(None),
    voice_file: Optional[UploadFile] = File(None),
    trigger_obs: bool = Form(False),
    draft_theme_json: Optional[str] = Form(None)
):
    temp_voice = None
    voice_path = None

    if voice_file:
        temp_voice = os.path.join(TEMP_DIR, f"draft_{int(time.time()*1000)}.wav")
        with open(temp_voice, "wb") as f:
            f.write(await voice_file.read())
        voice_path = temp_voice
    elif char_id:
        existing_path = os.path.join(CHARACTERS_DIR, char_id, "voice.wav")
        if os.path.exists(existing_path):
            voice_path = existing_path

    if not voice_path or not os.path.exists(voice_path):
        raise HTTPException(status_code=400, detail="Семпл голоса не передан и не найден.")

    try:
        wav_bytes, duration = generate_voice(text, voice_path, ref_text, speed)
        
        if trigger_obs:
            draft_theme = None
            if draft_theme_json:
                try:
                    draft_theme = json.loads(draft_theme_json)
                except Exception:
                    pass

            ws_manager.broadcast_sync({
                "event": "mita_dialogue",
                "text": text,
                "duration": duration,
                "char_id": char_id or get_active_character_id(),
                "draft_theme": draft_theme
            })

        return Response(content=wav_bytes, media_type="audio/wav")
    finally:
        if temp_voice and os.path.exists(temp_voice):
            try: os.remove(temp_voice)
            except Exception: pass

# ==================== МГНОВЕННОЕ ПРЕВЬЮ ОВЕРЛЕЯ БЕЗ GPU ====================
@app.post("/api/trigger_overlay_preview")
def api_trigger_overlay_preview(data: dict):
    text = data.get("text", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Пустой текст.")
        
    duration = float(data.get("duration", 3.5))
    char_id = data.get("char_id") or get_active_character_id()
    draft_theme = data.get("draft_theme")

    ws_manager.broadcast_sync({
        "event": "mita_dialogue",
        "text": text,
        "duration": duration,
        "char_id": char_id,
        "draft_theme": draft_theme
    })
    return {"status": "ok", "delivered": True}

@app.post("/api/characters/save")
async def api_save_character(
    char_id: str = Form(...),
    name: str = Form(...),
    reference_text: str = Form(...),
    speed: float = Form(1.0),
    theme_json: str = Form(...),
    voice_file: Optional[UploadFile] = File(None),
    avatar_file: Optional[UploadFile] = File(None)
):
    char_id = re.sub(r'[^a-zA-Z0-9_\-]', '', char_id).lower()
    if not char_id:
        raise HTTPException(status_code=400, detail="Недопустимый ID персонажа.")

    char_dir = os.path.join(CHARACTERS_DIR, char_id)
    os.makedirs(char_dir, exist_ok=True)

    voice_path = os.path.join(char_dir, "voice.wav")
    if voice_file:
        with open(voice_path, "wb") as f:
            f.write(await voice_file.read())

    avatar_path = os.path.join(char_dir, "avatar.png")
    if avatar_file:
        with open(avatar_path, "wb") as f:
            f.write(await avatar_file.read())

    try:
        theme = json.loads(theme_json)
    except Exception:
        theme = DEFAULT_PRESET["theme"]

    presets = load_presets()
    presets[char_id] = {
        "name": name,
        "reference_text": reference_text,
        "speed": speed,
        "theme": theme
    }
    save_presets(presets)

    if not get_active_character_id():
        set_active_character_id(char_id)

    return {"status": "ok", "char_id": char_id}

@app.delete("/api/characters/{char_id}")
def api_delete_character(char_id: str):
    presets = load_presets()
    if char_id in presets:
        del presets[char_id]
        save_presets(presets)
        char_dir = os.path.join(CHARACTERS_DIR, char_id)
        if os.path.exists(char_dir):
            shutil.rmtree(char_dir, ignore_errors=True)
        if get_active_character_id() == char_id:
            set_active_character_id(list(presets.keys())[0] if presets else "")
    return {"status": "ok"}

class SpeakRequest(BaseModel):
    text: str
    character: Optional[str] = None
    speed: Optional[float] = None

@app.post("/speak")
def api_speak(request: SpeakRequest):
    raw_text = request.text.strip()
    if not raw_text:
        raise HTTPException(status_code=400, detail="Пустой текст.")

    presets = load_presets()
    char_id = request.character or get_active_character_id()
    if char_id not in presets:
        raise HTTPException(status_code=404, detail=f"Персонаж '{char_id}' не найден.")

    char_data = presets[char_id]
    voice_path = os.path.join(CHARACTERS_DIR, char_id, "voice.wav")
    if not os.path.exists(voice_path):
        raise HTTPException(status_code=404, detail=f"Файл voice.wav для '{char_id}' не найден.")

    speed = request.speed or char_data.get("speed", 1.0)
    ref_text = char_data.get("reference_text", "")

    try:
        print(f"[SPEAK] Персонаж: {char_data.get('name', char_id)} (ID: {char_id}) | Скорость: {speed}")
        wav_bytes, duration = generate_voice(raw_text, voice_path, ref_text, speed)

        ws_manager.broadcast_sync({
            "event": "mita_dialogue",
            "text": raw_text,
            "duration": duration,
            "char_id": char_id
        })

        return Response(content=wav_bytes, media_type="audio/wav")
    except Exception as e:
        print(f"[SPEAK ERROR] Ошибка генерации: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    cfg = load_config()
    host = cfg.get("host", "127.0.0.1")
    port = int(cfg.get("port", 8765))
    
    if cfg.get("auto_open_browser", True):
        threading.Timer(1.0, lambda: webbrowser.open(f"http://127.0.0.1:{port}/dashboard")).start()
        
    uvicorn.run(app, host=host, port=port, log_level="info")