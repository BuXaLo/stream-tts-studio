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
    assert "CreateWindowExW.argtypes" in source
    assert "RegisterClassW.argtypes" in source
    assert "GetMessageW.argtypes" in source
    assert "Shell_NotifyIconW.argtypes" in source
    assert "CreateMutexW.argtypes" in source
    assert "GetLastError.restype" in source
    assert "Ошибка цикла сообщений системного трея" in source
    assert "LoadIconW(None" not in source
    assert '"/launcher-start"' in source
    assert '"/launcher-stop"' in source
    assert 'return self.backend_url + "/dashboard/"' in source
    assert "def open_monitor_window(url):" in source
    assert '"--app=" + url' in source
    assert '"/open-dashboard"' in source
    assert "open_monitor_window(monitor_url)" in source
    assert "open_monitor_window(self.monitor_url)" in source
    assert "Открыть монитор" in source
    assert "Открыть Dashboard" in source
    assert "Выход" in source
    assert "favicon.ico" in source
    assert "STUDIO_MONITOR_ORIGIN" in source
    assert "TTS Studio — ошибка запуска" in source
    assert "CreateMutexW" in source
    main_start = source.index("def main():")
    assert source.index("tray.start()", main_start) < source.index("controller.start_backend()", main_start)
