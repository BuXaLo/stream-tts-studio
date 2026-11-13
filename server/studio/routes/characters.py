"""Character and preset management API routes."""
import json
import logging
import math
import os
import re
import shutil
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile


_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _normalize_theme(raw_theme, default_theme):
    base = dict(default_theme) if isinstance(default_theme, dict) else {}
    if not isinstance(raw_theme, dict):
        return base
    merged = {**base, **raw_theme}
    if "text_stroke_color" in merged:
        stroke_color = merged["text_stroke_color"]
        if isinstance(stroke_color, str) and _HEX_COLOR_RE.fullmatch(stroke_color.strip()):
            merged["text_stroke_color"] = stroke_color.strip().lower()
        else:
            merged["text_stroke_color"] = base.get("text_stroke_color", "#000000")
    if "text_stroke_width" in merged:
        try:
            width = float(merged["text_stroke_width"])
            if not math.isfinite(width):
                raise ValueError("non-finite")
            merged["text_stroke_width"] = round(max(0.0, min(4.0, width)), 1)
        except (TypeError, ValueError, OverflowError):
            merged["text_stroke_width"] = base.get("text_stroke_width", 0.0)
    return merged


def create_characters_router(load_presets, save_presets, get_active_character_id, set_active_character_id, default_preset, require_character, characters_dir, presets_file, active_file, get_file_lock, write_bytes_atomic, convert_to_clean_wav, prompt_cache, logger=None):
    router = APIRouter()
    log = logger or logging.getLogger(__name__)

    @router.get("/api/presets")
    def get_presets_list():
        presets = load_presets()
        active = get_active_character_id()
        
        for char_id, data in presets.items():
            avatar_path = os.path.join(characters_dir, char_id, "avatar.png")
            has_avatar = os.path.exists(avatar_path)
            data["has_avatar"] = has_avatar
            data["avatar_url"] = f"/char_files/{char_id}/avatar.png" if has_avatar else ""
            
        return {"presets": presets, "active": active}
        
    @router.post("/api/presets/set_active")
    def api_set_active(data: dict):
        char_id = data.get("id")
        with get_file_lock(presets_file):
            presets = load_presets()
            if char_id not in presets:
                raise HTTPException(status_code=404, detail="Персонаж не найден.")
            with get_file_lock(active_file):
                set_active_character_id(char_id)
        return {"status": "ok", "active": char_id}
        
    @router.get("/api/active_overlay_config")
    def get_active_overlay_config(char_id: Optional[str] = None):
        presets = load_presets()
        target_id = char_id or get_active_character_id()
        char_data = presets.get(target_id, default_preset)
        
        avatar_url = ""
        if target_id and target_id in presets and re.fullmatch(r"[a-z0-9_-]+", target_id):
            avatar_path = os.path.join(characters_dir, target_id, "avatar.png")
            if os.path.exists(avatar_path):
                avatar_url = f"/char_files/{target_id}/avatar.png"
                
        theme = _normalize_theme(
            char_data.get("theme", default_preset["theme"]),
            default_preset["theme"]
        )
        return {
            "id": target_id,
            "name": char_data.get("name", "Персонаж"),
            "avatar": avatar_url,
            "theme": theme
        }
        

    @router.post("/api/characters/save")
    def api_save_character(
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
                raw_voice = voice_file.file.read()
                clean_wav = convert_to_clean_wav(raw_voice)
            except RuntimeError as exc:
                log.warning("Character voice conversion failed: %s", exc)
                raise HTTPException(status_code=400, detail="Не удалось обработать аудиофайл. Проверьте формат.")
                
        avatar_bytes = None
        if avatar_file:
            avatar_bytes = avatar_file.file.read()
            if not (
                avatar_bytes.startswith(b"\x89PNG\r\n\x1a\n")
                or avatar_bytes.startswith(b"\xff\xd8\xff")
            ):
                raise HTTPException(status_code=400, detail="Аватар должен быть файлом PNG или JPEG.")
                
        try:
            raw_theme = json.loads(theme_json)
            if not isinstance(raw_theme, dict):
                raise ValueError("theme must be an object")
            theme = _normalize_theme(raw_theme, default_preset["theme"])
        except (TypeError, ValueError):
            theme = dict(default_preset["theme"])
            
        with get_file_lock(presets_file):
            char_dir = os.path.join(characters_dir, char_id)
            os.makedirs(char_dir, exist_ok=True)
            voice_path = os.path.join(char_dir, "voice.wav")
            avatar_path = os.path.join(char_dir, "avatar.png")
            
            if clean_wav is not None:
                write_bytes_atomic(voice_path, clean_wav)
            if avatar_bytes is not None:
                write_bytes_atomic(avatar_path, avatar_bytes)
                
            presets = load_presets()
            presets[char_id] = {
                "name": name,
                "reference_text": reference_text,
                "speed": speed,
                "theme": theme
            }
            save_presets(presets)
            
            if clean_wav is not None:
                for cache_key in list(prompt_cache):
                    if cache_key.startswith(voice_path + "_"):
                        prompt_cache.pop(cache_key, None)
                        
            if not get_active_character_id():
                with get_file_lock(active_file):
                    set_active_character_id(char_id)
                    
        return {"status": "ok", "char_id": char_id}
        
    @router.delete("/api/characters/{char_id}")
    def api_delete_character(char_id: str):
        with get_file_lock(presets_file):
            presets = load_presets()
            if char_id not in presets:
            char_dir = os.path.join(characters_dir, char_id)
            if os.path.exists(char_dir):
                shutil.rmtree(char_dir, ignore_errors=True)
                return {"status": "ok"}
            del presets[char_id]
            save_presets(presets)
            with get_file_lock(active_file):
                if get_active_character_id() == char_id:
                    set_active_character_id(list(presets.keys())[0] if presets else "")
                    
        return {"status": "ok"}
        
    
    return router
