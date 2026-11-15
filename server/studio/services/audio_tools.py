"""FFmpeg-backed audio conversion helpers."""
import io
import os
import subprocess
import uuid
import wave

FFMPEG_PATH = TEMP_DIR = None
FFMPEG_TIMEOUT_SEC = 120


class AudioDecodeError(RuntimeError):
    """FFmpeg запущен, но не смог прочитать входной файл (проблема данных, а не сервера)."""


def configure_audio_tools(ffmpeg_path, temp_dir):
    global FFMPEG_PATH, TEMP_DIR
    FFMPEG_PATH = ffmpeg_path
    TEMP_DIR = temp_dir


def convert_to_clean_wav(input_bytes: bytes, start: float = 0.0, end: float = 0.0) -> bytes:
    """Любой аудио/видео-формат -> WAV mono 24 kHz PCM16 (формат референса CosyVoice).

    start/end (сек) вырезают фрагмент; end <= 0 означает "до конца".
    Каналы смешиваются, а не берётся только левый: голос не теряется,
    если он записан в один канал стерео.
    """
    if not os.path.isfile(FFMPEG_PATH):
        raise RuntimeError(f"FFmpeg не найден: {FFMPEG_PATH}")

    unique_id = uuid.uuid4().hex
    temp_in = os.path.join(TEMP_DIR, f"raw_in_{unique_id}")
    temp_out = os.path.join(TEMP_DIR, f"clean_out_{unique_id}.wav")
    try:
        with open(temp_in, "wb") as stream:
            stream.write(input_bytes)

        cmd = [FFMPEG_PATH, "-y", "-i", temp_in]
        # -ss/-t после -i: ffmpeg декодирует и отбрасывает лишнее, поэтому границы не зависят от кадров контейнера
        if start and start > 0:
            cmd += ["-ss", f"{start:.6f}"]
        if end and end > 0:
            cmd += ["-t", f"{max(end - (start or 0.0), 0.0):.6f}"]
        cmd += ["-vn", "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", temp_out]
        try:
            result = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=FFMPEG_TIMEOUT_SEC
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"FFmpeg превысил время обработки ({FFMPEG_TIMEOUT_SEC} секунд).") from exc

        if result.returncode != 0 or not os.path.isfile(temp_out):
            error_message = result.stderr.decode("utf-8", errors="ignore")[-500:]
            raise AudioDecodeError(f"FFmpeg decode error: {error_message}")

        with open(temp_out, "rb") as stream:
            return stream.read()
    finally:
        for path in (temp_in, temp_out):
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass


def wav_frame_count(wav_bytes: bytes) -> int:
    """Число аудио-кадров в WAV. Размер файла для этого не годится: ffmpeg пишет заголовок с LIST-блоком (~78 байт)."""
    with wave.open(io.BytesIO(wav_bytes)) as stream:
        return stream.getnframes()
