"""CosyVoice inference service; configured after environment and model setup."""
import gc
import io
import logging
import re
import time
import wave

import numpy as np
import torch

from studio.services.text import sanitize_text

cosyvoice = generation_lock = load_config = logger = None
PROMPT_CACHE = {}

def configure_tts(model, lock, config_loader, app_logger):
    global cosyvoice, generation_lock, load_config, logger
    cosyvoice = model
    generation_lock = lock
    load_config = config_loader
    logger = app_logger

def clear_vram():
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    gc.collect()

def clean_and_smooth_chunk(audio: np.ndarray, sr: int = 24000) -> np.ndarray:
    if len(audio) == 0:
        return audio
    audio = audio - np.mean(audio)
    fade_len = int(sr * 0.010)
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

def _generate_voice_impl(raw_text: str, voice_wav_path: str, ref_text: str, speed: float = 1.0) -> tuple[bytes, float]:
    global PROMPT_CACHE
    cfg = load_config()
    n_timesteps = int(cfg.get("n_timesteps", 6))

    with generation_lock:
        start_time = time.time()
        clean_text = sanitize_text(raw_text)
        sentences = [s.strip() for s in re.split(r'(?<=[.!?…\n])\s+', clean_text) if s.strip()]
        if not sentences:
            sentences = [clean_text]

        logger.info("TTS: старт генерации (%s предложений, %s steps)", len(sentences), n_timesteps)

        with torch.inference_mode():
            prompt_text = "You are a helpful assistant.<|endofprompt|>" + ref_text
            
            cache_key = f"{voice_wav_path}_{prompt_text}"
            if cache_key in PROMPT_CACHE:
                prompt_text_norm = PROMPT_CACHE[cache_key]
            else:
                prompt_text_norm = cosyvoice.frontend.text_normalize(prompt_text, split=False, text_frontend=True)
                if len(PROMPT_CACHE) >= 64:
                    PROMPT_CACHE.pop(next(iter(PROMPT_CACHE)))
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
            logger.info("TTS успешно: синтез %ss, длительность %ss", elapsed, duration)

            return numpy_to_wav(final_audio, sr), duration

def generate_voice(raw_text: str, voice_wav_path: str, ref_text: str, speed: float = 1.0) -> tuple[bytes, float]:
    try:
        return _generate_voice_impl(raw_text, voice_wav_path, ref_text, speed)
    except Exception:
        try:
            clear_vram()
        except Exception:
            logging.getLogger(__name__).exception("Ошибка очистки VRAM после сбоя генерации")
        raise

