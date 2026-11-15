from types import SimpleNamespace

import pytest

import studio.services.audio_tools as audio_tools


def test_ffmpeg_conversion_uses_timeout_and_returns_output(tmp_path, monkeypatch):
    ffmpeg = tmp_path / "ffmpeg.exe"
    ffmpeg.write_bytes(b"binary")
    audio_tools.configure_audio_tools(str(ffmpeg), str(tmp_path))
    calls = []

    def fake_run(command, **kwargs):
        calls.append(kwargs)
        with open(command[-1], "wb") as stream:
            stream.write(b"clean-wav")
        return SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setattr(audio_tools.subprocess, "run", fake_run)
    assert audio_tools.convert_to_clean_wav(b"source") == b"clean-wav"
    assert calls[0]["timeout"] == 120


def test_ffmpeg_timeout_is_reported_and_temp_files_are_removed(tmp_path, monkeypatch):
    ffmpeg = tmp_path / "ffmpeg.exe"
    ffmpeg.write_bytes(b"binary")
    audio_tools.configure_audio_tools(str(ffmpeg), str(tmp_path))

    def timeout(*args, **kwargs):
        raise audio_tools.subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(audio_tools.subprocess, "run", timeout)
    with pytest.raises(RuntimeError, match="120 секунд"):
        audio_tools.convert_to_clean_wav(b"source")
    assert list(tmp_path.glob("raw_in_*")) == []
    assert list(tmp_path.glob("clean_out_*")) == []


import math
import shutil
import struct
import wave


def test_ffmpeg_command_trims_with_ss_and_duration(tmp_path, monkeypatch):
    ffmpeg = tmp_path / "ffmpeg.exe"
    ffmpeg.write_bytes(b"binary")
    audio_tools.configure_audio_tools(str(ffmpeg), str(tmp_path))
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        with open(command[-1], "wb") as stream:
            stream.write(b"wav")
        return SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setattr(audio_tools.subprocess, "run", fake_run)
    audio_tools.convert_to_clean_wav(b"source", 1.5, 6.0)
    cmd = commands[0]
    assert cmd[cmd.index("-ss") + 1] == "1.500000"
    assert cmd[cmd.index("-t") + 1] == "4.500000"  # end - start
    assert (cmd[cmd.index("-ar") + 1], cmd[cmd.index("-ac") + 1], cmd[cmd.index("-c:a") + 1]) == ("24000", "1", "pcm_s16le")

    commands.clear()
    audio_tools.convert_to_clean_wav(b"source")
    assert "-ss" not in commands[0] and "-t" not in commands[0]


def test_ffmpeg_bad_input_raises_decode_error(tmp_path, monkeypatch):
    ffmpeg = tmp_path / "ffmpeg.exe"
    ffmpeg.write_bytes(b"binary")
    audio_tools.configure_audio_tools(str(ffmpeg), str(tmp_path))
    monkeypatch.setattr(audio_tools.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=1, stderr=b"bad"))
    with pytest.raises(audio_tools.AudioDecodeError):
        audio_tools.convert_to_clean_wav(b"junk")


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="реальный ffmpeg не найден")
def test_real_ffmpeg_trim_length_format_and_right_channel_kept(tmp_path):
    audio_tools.configure_audio_tools(shutil.which("ffmpeg"), str(tmp_path))
    src, sr = tmp_path / "src.wav", 44100
    with wave.open(str(src), "wb") as w:  # левый канал тишина, правый - голос
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b"".join(struct.pack("<hh", 0, int(12000 * math.sin(2 * math.pi * 440 * i / sr))) for i in range(6 * sr)))

    out = tmp_path / "out.wav"
    out.write_bytes(audio_tools.convert_to_clean_wav(src.read_bytes(), 1.0, 3.5))
    with wave.open(str(out)) as w:
        assert (w.getnchannels(), w.getframerate(), w.getsampwidth()) == (1, 24000, 2)
        assert w.getnframes() / w.getframerate() == pytest.approx(2.5, abs=0.01)
        samples = struct.unpack("<%dh" % w.getnframes(), w.readframes(w.getnframes()))
    assert max(abs(x) for x in samples) > 1000  # голос из правого канала не потерян


def _make_source(tmp_path, ext, codec):
    ffmpeg = shutil.which("ffmpeg")
    wav = tmp_path / "s.wav"
    sine = [ffmpeg, "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=f=440:d=6", "-ac", "1", "-ar", "44100"]
    audio_tools.subprocess.run(sine + [str(wav)], check=True)
    if ext == "wav":
        return wav
    dst = tmp_path / f"s.{ext}"
    res = audio_tools.subprocess.run([ffmpeg, "-loglevel", "error", "-y", "-i", str(wav), "-c:a", codec, str(dst)])
    if res.returncode != 0 or not dst.exists():
        pytest.skip(f"ffmpeg не умеет кодировать {ext} ({codec})")
    return dst


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="реальный ffmpeg не найден")
@pytest.mark.parametrize("ext,codec", [("wav", None), ("mp3", "libmp3lame"), ("m4a", "aac"), ("webm", "libopus"), ("ogg", "libvorbis")])
def test_real_ffmpeg_trim_duration_for_common_formats(tmp_path, ext, codec):
    audio_tools.configure_audio_tools(shutil.which("ffmpeg"), str(tmp_path))
    out = audio_tools.convert_to_clean_wav(_make_source(tmp_path, ext, codec).read_bytes(), 1.0, 3.5)
    assert audio_tools.wav_frame_count(out) / 24000 == pytest.approx(2.5, abs=0.05)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="реальный ffmpeg не найден")
def test_real_ffmpeg_range_outside_file_has_zero_frames_and_tail_is_short(tmp_path):
    audio_tools.configure_audio_tools(shutil.which("ffmpeg"), str(tmp_path))
    src = _make_source(tmp_path, "wav", None).read_bytes()
    beyond = audio_tools.convert_to_clean_wav(src, 10.0, 13.0)
    assert len(beyond) > 44  # ffmpeg пишет LIST-блок: проверка по размеру файла не работает
    assert audio_tools.wav_frame_count(beyond) == 0
    tail = audio_tools.convert_to_clean_wav(src, 5.99, 9.0)  # конец за пределами файла: обрезается по файлу
    assert 0 < audio_tools.wav_frame_count(tail) / 24000 < 0.05
