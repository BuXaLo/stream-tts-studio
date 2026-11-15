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


def test_monitor_resumes_startup_log_collection_for_each_backend_cycle():
    monitor = Path(__file__).resolve().parents[1] / "web" / "monitor" / "app.js"
    source = monitor.read_text(encoding="utf-8")

    assert "async function finishStartupCollection()" in source
    assert "let launcherStopRequestInProgress = false;" in source
    assert "startupComplete && !launcherStopRequestInProgress && !shutdownRequested" in source
    assert "startupCollectionActive && !launcherStopRequestInProgress" in source
    assert "if (launcherMode) await finishStartupCollection();" in source
    assert "finally {\n        if (launcherMode) launcherStopRequestInProgress = false;" in source
    assert 'startupCollectionActive = true;\n        daStartupState = "unknown";\n        daStartupConnectedMessageSeen = false;' in source
    assert 'if (launcherMode) {\n        startupCollectionActive = true;\n        launcherStopRequestInProgress = true;\n    }' in source
    assert 'if (launcherMode) startupCollectionActive = false;' in source
    assert source.count("startupOffset = 0;") == 1
    assert "logs.length = 0" not in source
    assert "seenEvents.clear()" not in source

def _load_launcher_for_window_tests():
    launcher_path = Path(__file__).resolve().parents[1] / "server" / "launcher.pyw"
    loader = importlib.machinery.SourceFileLoader("test_monitor_window_launcher", str(launcher_path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def test_choose_monitor_mode():
    module = _load_launcher_for_window_tests()

    mode, reason = module.choose_monitor_mode(" browser ", True, "1.2.3")
    assert mode == "browser"
    assert module.MONITOR_WINDOW_ENV in reason

    mode, reason = module.choose_monitor_mode("", False, None)
    assert mode == "browser"
    assert "pywebview" in reason

    mode, reason = module.choose_monitor_mode("", True, None)
    assert mode == "browser"
    assert "WebView2 Runtime" in reason

    mode, reason = module.choose_monitor_mode("", True, "1.2.3")
    assert mode == "webview"
    assert "1.2.3" in reason


def test_monitor_window_falls_back_when_webview_start_fails(monkeypatch):
    from types import SimpleNamespace

    module = _load_launcher_for_window_tests()
    module.exit_requested.clear()
    log_messages = []
    fallback_urls = []
    monkeypatch.setattr(
        module, "controller",
        SimpleNamespace(write_log=log_messages.append)
    )
    monkeypatch.setattr(module, "open_monitor_window", fallback_urls.append)

    class BrokenWebView:
        @staticmethod
        def create_window(*args, **kwargs):
            raise RuntimeError("WebView2 initialization failed")

    module.run_webview_monitor(BrokenWebView(), "http://127.0.0.1:1234/", lambda: None)

    assert fallback_urls == ["http://127.0.0.1:1234/"]
    assert any("Ошибка окна pywebview" in message for message in log_messages)
    assert module.monitor_window is None


def test_monitor_window_falls_back_after_load_timeout(monkeypatch):
    from types import SimpleNamespace

    module = _load_launcher_for_window_tests()
    module.exit_requested.clear()
    monkeypatch.setattr(module, "WINDOW_LOAD_TIMEOUT", 0)
    fallback_calls = []
    log_messages = []
    window = module.MonitorWindow(
        SimpleNamespace(), "http://127.0.0.1:1234/",
        log_messages.append, lambda: fallback_calls.append(True), lambda: None
    )
    window.window = SimpleNamespace(destroy=lambda: None)
    # Имитируем ситуацию, когда GUI-поток не завершился даже после destroy().
    window.finished.wait = lambda timeout=None: False

    window._watch_load()

    assert not window.active
    assert fallback_calls == [True]
    assert any("не загрузило монитор" in message for message in log_messages)

    # Повторный сигнал отката не должен открывать второе окно.
    window.fallback()
    assert fallback_calls == [True]


def test_open_monitor_window_uses_browser_when_webview_show_fails(monkeypatch):
    from types import SimpleNamespace

    module = _load_launcher_for_window_tests()
    log_messages = []
    opened_urls = []

    class BrokenWindow:
        @staticmethod
        def show():
            raise RuntimeError("window handle is no longer valid")

    window = module.MonitorWindow(
        SimpleNamespace(), "http://127.0.0.1:1234/",
        log_messages.append, lambda: None, lambda: None
    )
    window.window = BrokenWindow()
    window.loaded.set()
    module.monitor_window = window

    monkeypatch.setattr(module.os.path, "isfile", lambda path: False)
    monkeypatch.setattr(module.webbrowser, "open", lambda url: opened_urls.append(url))

    module.open_monitor_window("http://127.0.0.1:1234/")

    assert opened_urls == ["http://127.0.0.1:1234/"]
    assert any("Не удалось показать окно монитора" in message for message in log_messages)

