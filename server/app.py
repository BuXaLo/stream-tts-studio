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
    with get_file_lock(PRESETS_FILE):
        presets = load_presets()
        if char_id not in presets:
            raise HTTPException(status_code=404, detail="Персонаж не найден.")
        with get_file_lock(ACTIVE_FILE):
            set_active_character_id(char_id)
    return {"status": "ok", "active": char_id}

@app.get("/api/active_overlay_config")
def get_active_overlay_config(char_id: Optional[str] = None):
    presets = load_presets()
    target_id = char_id or get_active_character_id()
    char_data = presets.get(target_id, DEFAULT_PRESET)
    
    avatar_url = ""
    if target_id and target_id in presets and re.fullmatch(r"[a-z0-9_-]+", target_id):
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
def api_upload_font(file: UploadFile = File(...)):
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
    if os.path.exists(dest_path):
        is_duplicate = True
    else:
        write_bytes_atomic(dest_path, file.file.read())
        is_duplicate = False

    return {
        "status": "ok",
        "name": clean_base,
        "file": final_filename,
        "url": f"/fonts/custom/{final_filename}",
        "is_duplicate": is_duplicate
    }

@app.post("/api/trim_and_transcribe")
def api_trim_and_transcribe(
    audio: UploadFile = File(...),
    start: float = Form(0.0),
    end: float = Form(0.0)
):
    temp_in = os.path.join(TEMP_DIR, f"trim_in_{int(time.time()*1000)}.wav")
    temp_out = os.path.join(TEMP_DIR, f"trim_out_{int(time.time()*1000)}.wav")
    whisper_model = None
    device = "cpu"
    try:
        if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end < 0 or (end > 0 and end <= start):
            raise HTTPException(status_code=400, detail="Некорректный диапазон обрезки аудио.")

        with open(temp_in, "wb") as stream:
            stream.write(audio.file.read())

        data, sr = sf.read(temp_in, dtype='float32')
        if data.ndim > 1:
            data = data[:, 0]

        start_frame = max(0, int(start * sr))
        end_frame = min(len(data), int(end * sr)) if end > 0 else len(data)
        if start_frame >= end_frame:
            raise HTTPException(status_code=400, detail="Выбранный диапазон аудио пуст.")

        sf.write(temp_out, data[start_frame:end_frame], sr, format="WAV", subtype="PCM_16")
        device = "cuda" if torch.cuda.is_available() else "cpu"
        with generation_lock:
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
            text = " ".join([segment.text.strip() for segment in segments]).strip()

        logger.info(
            "Whisper: язык %s (вероятность %s%%), распознано %s символов",
            info.language, round(info.language_probability * 100, 1), len(text)
        )
        with open(temp_out, "rb") as stream:
            wav_bytes = stream.read()
        return {"text": text, "audio_base64": base64.b64encode(wav_bytes).decode("utf-8")}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Whisper processing failed")
        raise HTTPException(status_code=500, detail=f"Ошибка обработки: {str(exc)}")
    finally:
        if whisper_model is not None:
            del whisper_model
            if device == "cuda":
                clear_vram()
        for path in (temp_in, temp_out):
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass

@app.post("/api/normalize_audio")
def api_normalize_audio(
    audio: UploadFile = File(...),
    target_gain: float = Form(0.95)
):
    if not math.isfinite(target_gain) or not 0.1 <= target_gain <= 1.0:
        raise HTTPException(status_code=400, detail="target_gain должен быть в диапазоне 0.1–1.0.")
    try:
        in_bio = io.BytesIO(audio.file.read())
        data, sr = sf.read(in_bio, dtype='float32')
        if data.size == 0:
            raise HTTPException(status_code=400, detail="Аудиофайл пуст.")
        if data.ndim > 1:
            data = data[:, 0]

        data = data - np.mean(data)
        peak = np.max(np.abs(data))
        if peak > 0.0001:
            data = np.clip(data * (target_gain / peak), -0.99, 0.99)

        out_bio = io.BytesIO()
        sf.write(out_bio, data, sr, format="WAV", subtype="PCM_16")
        return Response(content=out_bio.getvalue(), media_type="audio/wav")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Audio normalization failed")
        raise HTTPException(status_code=500, detail=f"Ошибка нормализации: {str(exc)}")

@app.post("/api/isolate_vocal")
def api_isolate_vocal(
    audio: UploadFile = File(...),
    shifts: int = Form(2)
):
    if not 1 <= shifts <= 10:
        raise HTTPException(status_code=400, detail="shifts должен быть в диапазоне 1–10.")
    device = "cpu"
    model = None
    try:
        raw_bytes = audio.file.read()
        in_bio = io.BytesIO(raw_bytes)
        from demucs.pretrained import get_model
        from demucs.apply import apply_model

        device = "cuda" if torch.cuda.is_available() else "cpu"
        with generation_lock:
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
                sources = apply_model(
                    model, wav_input[None], device=device,
                    shifts=shifts, split=True, progress=False
                )[0]

            vocal_idx = model.sources.index("vocals")
            vocals = sources[vocal_idx]
            vocal_mono = vocals[0:1, :]
            if orig_sr != model.samplerate:
                resample_back = torchaudio.transforms.Resample(model.samplerate, orig_sr).to(device)
                vocal_mono = resample_back(vocal_mono)

            vocal_np = vocal_mono.squeeze(0).cpu().numpy()
            out_bio = io.BytesIO()
            sf.write(out_bio, vocal_np, orig_sr, format="WAV", subtype="PCM_16")

        return Response(content=out_bio.getvalue(), media_type="audio/wav")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Demucs vocal isolation failed")
        raise HTTPException(status_code=500, detail=f"Ошибка очистки голоса: {str(exc)}")
    finally:
        if model is not None:
            del model
        if device == "cuda":
            clear_vram()

@app.post("/api/convert_to_telegram_ogg")
def api_convert_to_telegram_ogg(audio: UploadFile = File(...)):
    if not os.path.isfile(FFMPEG_PATH):
        raise HTTPException(status_code=500, detail=f"FFmpeg не найден: {FFMPEG_PATH}")

    temp_wav = os.path.join(TEMP_DIR, f"conv_{int(time.time()*1000)}.wav")
    temp_ogg = os.path.join(TEMP_DIR, f"conv_{int(time.time()*1000)}.ogg")
    try:
        with open(temp_wav, "wb") as stream:
            stream.write(audio.file.read())

        cmd = [
            FFMPEG_PATH, "-y", "-i", temp_wav,
            "-c:a", "libopus", "-b:a", "32k", "-vbr", "on",
            "-compression_level", "10", "-frame_duration", "60",
            "-application", "voip", "-ar", "48000", "-ac", "1",
            temp_ogg
        ]
        try:
            result = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, timeout=120
            )
        except subprocess.TimeoutExpired as exc:
            raise HTTPException(status_code=504, detail="FFmpeg превысил время обработки (120 секунд).") from exc

        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg error: {result.stderr[-200:]}")
        with open(temp_ogg, "rb") as stream:
            ogg_bytes = stream.read()
        return Response(content=ogg_bytes, media_type="audio/ogg")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Telegram OGG conversion failed")
        raise HTTPException(status_code=500, detail=f"Ошибка конвертации: {str(exc)}")
    finally:
        for path in (temp_wav, temp_ogg):
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass

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

    if not text.strip() or not has_speakable_content(text):
        raise HTTPException(status_code=400, detail="Нет текста для озвучки.")
    if not math.isfinite(speed):
        raise HTTPException(status_code=400, detail="Некорректное значение speed.")
    speed = max(0.5, min(2.0, speed))

    if voice_file:
        try:
            raw_draft = await voice_file.read()
            clean_draft = await asyncio.to_thread(convert_to_clean_wav, raw_draft)
        except RuntimeError as e:
            logger.warning("Draft audio conversion failed: %s", e)
            raise HTTPException(status_code=400, detail="Не удалось декодировать аудиофайл сэмпла.")

        temp_voice = os.path.join(TEMP_DIR, f"draft_{int(time.time()*1000)}.wav")
        with open(temp_voice, "wb") as f:
            f.write(clean_draft)
        voice_path = temp_voice
    elif char_id:
        require_character(char_id)
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
                "text": sanitize_overlay_text(text),
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
        "text": sanitize_overlay_text(text),
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

    clean_wav = None
    if voice_file:
        try:
            raw_voice = await voice_file.read()
            clean_wav = await asyncio.to_thread(convert_to_clean_wav, raw_voice)
        except RuntimeError as exc:
            logger.warning("Character voice conversion failed: %s", exc)
            raise HTTPException(status_code=400, detail="Не удалось обработать аудиофайл. Проверьте формат.")

    avatar_bytes = None
    if avatar_file:
        avatar_bytes = await avatar_file.read()
        if not (
            avatar_bytes.startswith(b"\x89PNG\r\n\x1a\n")
            or avatar_bytes.startswith(b"\xff\xd8\xff")
        ):
            raise HTTPException(status_code=400, detail="Аватар должен быть файлом PNG или JPEG.")

    try:
        theme = json.loads(theme_json)
        if not isinstance(theme, dict):
            raise ValueError("theme must be an object")
    except (TypeError, ValueError):
        theme = DEFAULT_PRESET["theme"]

    char_dir = os.path.join(CHARACTERS_DIR, char_id)
    os.makedirs(char_dir, exist_ok=True)
    voice_path = os.path.join(char_dir, "voice.wav")
    avatar_path = os.path.join(char_dir, "avatar.png")

    if clean_wav is not None:
        write_bytes_atomic(voice_path, clean_wav)
    if avatar_bytes is not None:
        write_bytes_atomic(avatar_path, avatar_bytes)

    with get_file_lock(PRESETS_FILE):
        presets = load_presets()
        presets[char_id] = {
            "name": name,
            "reference_text": reference_text,
            "speed": speed,
            "theme": theme
        }
        save_presets(presets)

    if clean_wav is not None:
        for cache_key in list(PROMPT_CACHE):
            if cache_key.startswith(voice_path + "_"):
                PROMPT_CACHE.pop(cache_key, None)

    if not get_active_character_id():
        with get_file_lock(ACTIVE_FILE):
            set_active_character_id(char_id)

    return {"status": "ok", "char_id": char_id}

@app.delete("/api/characters/{char_id}")
def api_delete_character(char_id: str):
    with get_file_lock(PRESETS_FILE):
        presets = load_presets()
        if char_id not in presets:
            return {"status": "ok"}
        del presets[char_id]
        save_presets(presets)
        with get_file_lock(ACTIVE_FILE):
            if get_active_character_id() == char_id:
                set_active_character_id(list(presets.keys())[0] if presets else "")

    char_dir = os.path.join(CHARACTERS_DIR, char_id)
    if os.path.exists(char_dir):
        shutil.rmtree(char_dir, ignore_errors=True)
    return {"status": "ok"}

class SpeakRequest(BaseModel):
    text: str
    character: Optional[str] = None
    speed: Optional[float] = None

@app.post("/speak")
def api_speak(request: SpeakRequest):
    raw_text = request.text.strip()
    if not raw_text or not has_speakable_content(raw_text):
        raise HTTPException(status_code=400, detail="Нет текста для озвучки.")

    presets = load_presets()
    char_id = request.character or get_active_character_id()
    if char_id not in presets:
        raise HTTPException(status_code=404, detail=f"Персонаж '{char_id}' не найден.")

    char_data = presets[char_id]
    voice_path = os.path.join(CHARACTERS_DIR, char_id, "voice.wav")
    if not os.path.exists(voice_path):
        raise HTTPException(status_code=404, detail=f"Файл voice.wav для '{char_id}' не найден.")

    try:
        if request.speed is not None:
            requested_speed = float(request.speed)
            if not math.isfinite(requested_speed):
                raise ValueError("speed must be finite")
            speed = max(0.5, min(2.0, requested_speed))
        else:
            speed = char_data.get("speed", 1.0)
    except (TypeError, ValueError, OverflowError):
        raise HTTPException(status_code=400, detail="Некорректное значение speed.")
    ref_text = char_data.get("reference_text", "")

    try:
        logger.info("SPEAK: персонаж %s (ID: %s), скорость %s", char_data.get("name", char_id), char_id, speed)
        wav_bytes, duration = generate_voice(raw_text, voice_path, ref_text, speed)

        ws_manager.broadcast_sync({
            "event": "mita_dialogue",
            "text": sanitize_overlay_text(raw_text),
            "duration": duration,
            "char_id": char_id
        })

        return Response(content=wav_bytes, media_type="audio/wav")
    except torch.cuda.OutOfMemoryError:
        logging.getLogger(__name__).exception("CUDA out of memory during /speak")
        raise HTTPException(status_code=503, detail="Недостаточно видеопамяти для генерации.")
    except HTTPException:
        raise
    except Exception as e:
        logging.getLogger(__name__).exception("Ошибка генерации /speak")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    cfg = load_config()
    host = cfg.get("host", "127.0.0.1")
    port = int(cfg.get("port", 8765))
    
    if cfg.get("auto_open_browser", True):
        browser_host = "127.0.0.1" if host == "0.0.0.0" else ("[{}]".format(host) if ":" in host and not host.startswith("[") else host)
        threading.Timer(1.0, lambda: webbrowser.open(f"http://{browser_host}:{port}/dashboard")).start()
        
    uvicorn.run(app, host=host, port=port, log_level="info")
