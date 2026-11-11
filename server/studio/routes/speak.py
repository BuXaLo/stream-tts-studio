"""Public speech synthesis endpoint."""
import logging
import math
import os
from typing import Optional

import torch
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel


class SpeakRequest(BaseModel):
    text: str
    character: Optional[str] = None
    speed: Optional[float] = None


def create_speak_router(load_presets, get_active_character_id, characters_dir, generate_voice, ws_manager, has_speakable_content, sanitize_overlay_text, logger=None):
    router = APIRouter()
    log = logger or logging.getLogger(__name__)

    @router.post("/speak")
    def api_speak(request: SpeakRequest):
        raw_text = request.text.strip()
        if not raw_text or not has_speakable_content(raw_text):
            raise HTTPException(status_code=400, detail="Нет текста для озвучки.")
    
        presets = load_presets()
        char_id = request.character or get_active_character_id()
        if char_id not in presets:
            raise HTTPException(status_code=404, detail=f"Персонаж '{char_id}' не найден.")
    
        char_data = presets[char_id]
        voice_path = os.path.join(characters_dir, char_id, "voice.wav")
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
            log.info("SPEAK: персонаж %s (ID: %s), скорость %s", char_data.get("name", char_id), char_id, speed)
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
    

    return router
