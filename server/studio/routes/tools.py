"""Audio processing, draft TTS and overlay preview API routes."""
import asyncio
import base64
import io
import json
import logging
import math
import os
import subprocess
import time
from typing import Optional

import numpy as np
import soundfile as sf
import torch
import torchaudio
from faster_whisper import WhisperModel
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response


def create_tools_router(temp_dir, whisper_path, ffmpeg_path, generation_lock, convert_to_clean_wav, clear_vram, generate_voice, has_speakable_content, sanitize_overlay_text, ws_manager, require_character, characters_dir, get_active_character_id, logger=None):
    router = APIRouter()
    log = logger or logging.getLogger(__name__)
    TEMP_DIR = temp_dir
    WHISPER_PATH = whisper_path
    FFMPEG_PATH = ffmpeg_path

    @router.post("/api/trim_and_transcribe")
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
    
            log.info(
                "Whisper: язык %s (вероятность %s%%), распознано %s символов",
                info.language, round(info.language_probability * 100, 1), len(text)
            )
            with open(temp_out, "rb") as stream:
                wav_bytes = stream.read()
            return {"text": text, "audio_base64": base64.b64encode(wav_bytes).decode("utf-8")}
        except HTTPException:
            raise
        except Exception as exc:
            log.exception("Whisper processing failed")
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
    
    @router.post("/api/normalize_audio")
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
            log.exception("Audio normalization failed")
            raise HTTPException(status_code=500, detail=f"Ошибка нормализации: {str(exc)}")
    
    @router.post("/api/isolate_vocal")
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
            log.exception("Demucs vocal isolation failed")
            raise HTTPException(status_code=500, detail=f"Ошибка очистки голоса: {str(exc)}")
        finally:
            if model is not None:
                del model
            if device == "cuda":
                clear_vram()
    
    @router.post("/api/convert_to_telegram_ogg")
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
            log.exception("Telegram OGG conversion failed")
            raise HTTPException(status_code=500, detail=f"Ошибка конвертации: {str(exc)}")
        finally:
            for path in (temp_wav, temp_ogg):
                if os.path.exists(path):
                    try:
                        os.remove(path)
                    except OSError:
                        pass
    
    @router.post("/api/test_draft_tts")
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
                log.warning("Draft audio conversion failed: %s", e)
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
    @router.post("/api/trigger_overlay_preview")
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
    

    return router
