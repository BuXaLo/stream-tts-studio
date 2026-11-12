from pathlib import Path
import importlib.machinery
import importlib.util
import threading
import urllib.request
from http.server import ThreadingHTTPServer


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

def test_startup_log_offset_returns_only_appended_bytes(tmp_path, monkeypatch):
    launcher_path = Path(__file__).resolve().parents[1] / "server" / "launcher.pyw"
    loader = importlib.machinery.SourceFileLoader("test_monitor_launcher_module", str(launcher_path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)

    log_path = tmp_path / "startup.log"
    initial = "first line\n".encode("utf-8")
    appended = "новая строка\n".encode("utf-8")
    log_path.write_bytes(initial)
    monkeypatch.setattr(module, "LOG_FILE", str(log_path))

    server = ThreadingHTTPServer(("127.0.0.1", 0), module.MonitorLauncherHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = "http://127.0.0.1:{}/startup-log".format(server.server_address[1])
    try:
        with urllib.request.urlopen(base_url + "?offset=0", timeout=3) as response:
            first_payload = response.read()
            offset = int(response.headers["X-Log-Offset"])
        assert first_payload == initial
        assert offset == len(initial)

        with log_path.open("ab") as stream:
            stream.write(appended)

        with urllib.request.urlopen(base_url + "?offset={}".format(offset), timeout=3) as response:
            second_payload = response.read()
            next_offset = int(response.headers["X-Log-Offset"])
        assert second_payload == appended
        assert next_offset == len(initial) + len(appended)

        with urllib.request.urlopen(base_url, timeout=3) as response:
            legacy_payload = response.read()
        assert legacy_payload == initial + appended
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
