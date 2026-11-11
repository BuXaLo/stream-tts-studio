"""FFmpeg-backed audio conversion helpers."""
import os
import subprocess
import time

FFMPEG_PATH = TEMP_DIR = None

def configure_audio_tools(ffmpeg_path, temp_dir):
    global FFMPEG_PATH, TEMP_DIR
    FFMPEG_PATH = ffmpeg_path
    TEMP_DIR = temp_dir

def convert_to_clean_wav(input_bytes: bytes) -> bytes:
    if not os.path.isfile(FFMPEG_PATH):
        raise RuntimeError(f"FFmpeg не найден: {FFMPEG_PATH}")

    timestamp = int(time.time() * 1000)
    temp_in = os.path.join(TEMP_DIR, f"raw_in_{timestamp}")
    temp_out = os.path.join(TEMP_DIR, f"clean_out_{timestamp}.wav")
    try:
        with open(temp_in, "wb") as stream:
            stream.write(input_bytes)

        cmd = [
            FFMPEG_PATH, "-y", "-i", temp_in,
            "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", temp_out
        ]
        try:
            result = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("FFmpeg превысил время обработки (120 секунд).") from exc

        if result.returncode != 0 or not os.path.isfile(temp_out):
            error_message = result.stderr.decode("utf-8", errors="ignore")[-500:]
            raise RuntimeError(f"FFmpeg decode error: {error_message}")

        with open(temp_out, "rb") as stream:
            return stream.read()
    finally:
        for path in (temp_in, temp_out):
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass

