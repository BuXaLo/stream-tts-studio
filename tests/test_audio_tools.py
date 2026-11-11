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
