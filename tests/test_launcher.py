from pathlib import Path


def test_monitor_launcher_tray_and_backend_lifecycle():
    launcher = Path(__file__).resolve().parents[1] / "server" / "launcher.pyw"
    source = launcher.read_text(encoding="utf-8")
    compile(source, str(launcher), "exec")

    assert "ThreadingHTTPServer" in source
    assert 'path == "/startup-log"' in source
    assert "stdout=self.log_stream" in source
    assert "stderr=subprocess.STDOUT" in source
    assert "Win32TrayIcon" in source
    assert "Shell_NotifyIconW" in source
    assert '"/launcher-start"' in source
    assert '"/open-dashboard"' in source
    assert "webbrowser.open(monitor_url, new=2)" in source
    assert "Открыть монитор" in source
    assert "Открыть Dashboard" in source
    assert "Выход" in source
    assert "favicon.ico" in source
    assert "STUDIO_MONITOR_ORIGIN" in source
    assert "TTS Studio — ошибка запуска" in source
    assert "CreateMutexW" in source
    assert source.index("tray.start()") < source.index("controller.start_backend()")
