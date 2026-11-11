from pathlib import Path


def test_monitor_window_starts_before_backend_and_shows_startup_log():
    launcher = Path(__file__).resolve().parents[1] / "server" / "launcher.pyw"
    source = launcher.read_text(encoding="utf-8")
    compile(source, str(launcher), "exec")
    assert "ThreadingHTTPServer" in source
    assert 'path == "/startup-log"' in source
    assert "stdout=log_stream" in source
    assert "stderr=subprocess.STDOUT" in source
    assert source.index("open_monitor_window(monitor_url)") < source.index("child = subprocess.Popen(")
    assert 'STUDIO_MONITOR_ORIGIN' in source
    assert "TTS Studio — ошибка запуска" in source
