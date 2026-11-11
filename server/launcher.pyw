# -*- coding: utf-8 -*-
"""Monitor launcher with a persistent Windows notification-area icon."""
import ctypes
from ctypes import wintypes
import json
import os
import subprocess
import threading
import time
import traceback
import urllib.request
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SERVER_DIR)
WEB_DIR = os.path.join(BASE_DIR, "web", "monitor")
ICON_FILE = os.path.join(BASE_DIR, "web", "dashboard", "favicon.ico")
LOG_DIR = os.path.join(BASE_DIR, "logs")
LOG_FILE = os.path.join(LOG_DIR, "startup.log")
APP_FILE = os.path.join(SERVER_DIR, "app.py")
PYTHON_EXE = os.path.join(BASE_DIR, "cosyvoice3", "upy", "python.exe")
os.makedirs(LOG_DIR, exist_ok=True)

state = {"status": "starting", "backend_url": "", "detail": "", "pid": None, "exit_code": None}
state_lock = threading.RLock()
exit_requested = threading.Event()
controller = None
_singleton_handle = None


class LauncherController:
    def __init__(self, backend_url, monitor_port, log_stream):
        self.backend_url = backend_url
        self.monitor_port = monitor_port
        self.log_stream = log_stream
        self.child = None
        self.lock = threading.RLock()
        self.log_lock = threading.Lock()
        self.write_log("Launcher готов.")
        self.set_state(status="starting", backend_url=backend_url, detail="Запуск backend", pid=None, exit_code=None)

    @staticmethod
    def set_state(**values):
        with state_lock:
            state.update(values)

    def write_log(self, message):
        with self.log_lock:
            self.log_stream.write("[{}] {}\n".format(
                datetime.now().astimezone().isoformat(timespec="seconds"), message
            ))
            self.log_stream.flush()

    def start_backend(self):
        with self.lock:
            if self.child is not None and self.child.poll() is None:
                return False
            if not os.path.isfile(PYTHON_EXE):
                raise FileNotFoundError("Не найден portable python.exe: {}".format(PYTHON_EXE))
            if not os.path.isfile(APP_FILE):
                raise FileNotFoundError("Не найден backend: {}".format(APP_FILE))
            self.write_log("Запуск backend.")
            child_env = os.environ.copy()
            child_env["STUDIO_MONITOR_MODE"] = "1"
            child_env["STUDIO_MONITOR_ORIGIN"] = "http://127.0.0.1:{}".format(self.monitor_port)
            child_env["PYTHONUNBUFFERED"] = "1"
            self.child = subprocess.Popen(
                [PYTHON_EXE, "-u", APP_FILE], cwd=BASE_DIR, env=child_env,
                stdout=self.log_stream, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )
            self.set_state(status="starting", detail="Запуск backend", pid=self.child.pid, exit_code=None)
            return True

    def refresh(self):
        with self.lock:
            child = self.child
            if child is None:
                return
            code = child.poll()
            if code is None:
                with state_lock:
                    starting = state["status"] == "starting"
                if starting:
                    try:
                        with urllib.request.urlopen(self.backend_url + "/monitor", timeout=0.5) as response:
                            if response.status == 200:
                                self.set_state(status="ready", detail="Backend готов", pid=child.pid)
                    except Exception:
                        pass
                return
            with state_lock:
                finished = state["pid"] != child.pid or state["status"] in ("stopped", "error")
            if finished:
                return
            if code == 0:
                self.set_state(status="stopped", detail="Студия завершила работу", exit_code=code)
            else:
                self.set_state(status="error", detail="Backend завершился с кодом {}".format(code), exit_code=code)
            self.write_log("Backend завершён, код: {}".format(code))

    def dashboard_url(self):
        return self.backend_url + "/"

    def stop_backend(self):
        with self.lock:
            child = self.child
        if child is None or child.poll() is not None:
            self.refresh()
            return
        try:
            request = urllib.request.Request(self.backend_url + "/api/monitor/shutdown", data=b"", method="POST")
            with urllib.request.urlopen(request, timeout=3):
                pass
        except Exception as exc:
            self.write_log("Ошибка запроса штатного выключения: {}".format(exc))
        try:
            child.wait(timeout=45)
        except subprocess.TimeoutExpired:
            self.write_log("Backend не завершился за 45 секунд; завершаю процесс.")
            child.terminate()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        self.refresh()


class MonitorLauncherHandler(BaseHTTPRequestHandler):
    def _local_request(self):
        ip = self.client_address[0]
        host = self.headers.get("Host", "").split(":", 1)[0].strip("[]").lower()
        origin = self.headers.get("Origin")
        expected_origin = "http://127.0.0.1:{}".format(self.server.server_address[1])
        return (
            ip in ("127.0.0.1", "::1")
            and host in ("127.0.0.1", "localhost")
            and (not origin or origin == expected_origin)
        )

    def do_GET(self):
        if not self._local_request():
            self.send_error(403)
            return
        path = urlsplit(self.path).path
        if path == "/launcher-status":
            controller.refresh()
            with state_lock:
                payload = json.dumps(state, ensure_ascii=False).encode("utf-8")
            self._send(200, "application/json; charset=utf-8", payload)
            return
        if path == "/startup-log":
            try:
                with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as stream:
                    content = stream.read()[-131072:]
            except OSError:
                content = ""
            self._send(200, "text/plain; charset=utf-8", content.encode("utf-8"))
            return
        assets = {
            "/": ("index.html", "text/html; charset=utf-8"),
            "/monitor": ("index.html", "text/html; charset=utf-8"),
            "/monitor/": ("index.html", "text/html; charset=utf-8"),
            "/monitor/index.html": ("index.html", "text/html; charset=utf-8"),
            "/monitor/app.js": ("app.js", "application/javascript; charset=utf-8"),
            "/monitor/style.css": ("style.css", "text/css; charset=utf-8"),
        }
        if path == "/favicon.ico":
            asset_path, content_type = ICON_FILE, "image/x-icon"
        else:
            asset = assets.get(path)
            if asset is None:
                self.send_error(404)
                return
            asset_path, content_type = os.path.join(WEB_DIR, asset[0]), asset[1]
        try:
            with open(asset_path, "rb") as stream:
                payload = stream.read()
        except OSError:
            self.send_error(404)
            return
        self._send(200, content_type, payload)

    def do_POST(self):
        if not self._local_request():
            self.send_error(403)
            return
        path = urlsplit(self.path).path
        if path == "/launcher-start":
            try:
                started = controller.start_backend()
                payload = json.dumps({"status": "starting" if started else "already_running"}).encode("utf-8")
                self._send(202 if started else 200, "application/json; charset=utf-8", payload)
            except Exception as exc:
                controller.set_state(status="error", detail="Не удалось запустить backend: {}".format(exc))
                controller.write_log("Ошибка запуска backend: {}".format(exc))
                payload = json.dumps({"detail": str(exc)}, ensure_ascii=False).encode("utf-8")
                self._send(500, "application/json; charset=utf-8", payload)
            return
        if path == "/open-dashboard":
            opened = webbrowser.open(controller.dashboard_url(), new=1)
            payload = json.dumps({"opened": bool(opened)}).encode("utf-8")
            self._send(200 if opened else 500, "application/json; charset=utf-8", payload)
            return
        self.send_error(404)

    def _send(self, status, content_type, payload):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format_string, *args):
        return


class Win32TrayIcon:
    WM_TRAY = 0x8001
    WM_COMMAND = 0x0111
    WM_CLOSE = 0x0010
    WM_DESTROY = 0x0002
    WM_LBUTTONDBLCLK = 0x0203
    WM_RBUTTONUP = 0x0205
    OPEN, DASHBOARD, EXIT = 1001, 1002, 1003

    def __init__(self, monitor_url, app_controller):
        self.monitor_url = monitor_url
        self.app_controller = app_controller
        self.ready = threading.Event()
        self.thread = None
        self.hwnd = None
        self.icon = None
        self.callback = None
        self.error = None
        self.class_name = "StreamTTSStudioTrayWindow"
        self.user32 = ctypes.windll.user32
        self.shell32 = ctypes.windll.shell32

    def start(self):
        self.thread = threading.Thread(target=self._run, name="studio-system-tray", daemon=True)
        self.thread.start()
        if not self.ready.wait(5):
            raise RuntimeError("Не удалось запустить системный трей.")
        if self.error:
            raise RuntimeError("Не удалось создать иконку системного трея: {}".format(self.error))

    def stop(self):
        if self.hwnd:
            self.user32.PostMessageW(self.hwnd, self.WM_CLOSE, 0, 0)
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=3)

    def _run(self):
        try:
            self._create_window()
        except Exception as exc:
            self.error = exc
            controller.write_log("Ошибка системного трея:\n{}".format(traceback.format_exc()))
        finally:
            self.ready.set()
        if self.error:
            return
        message = wintypes.MSG()
        while self.user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            self.user32.TranslateMessage(ctypes.byref(message))
            self.user32.DispatchMessageW(ctypes.byref(message))

    def _create_window(self):
        WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

        class WNDCLASSW(ctypes.Structure):
            _fields_ = [
                ("style", wintypes.UINT), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)
            ]

        class NOTIFYICONDATAW(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND),
                ("uID", wintypes.UINT), ("uFlags", wintypes.UINT),
                ("uCallbackMessage", wintypes.UINT), ("hIcon", wintypes.HICON),
                ("szTip", wintypes.WCHAR * 128), ("dwState", wintypes.DWORD),
                ("dwStateMask", wintypes.DWORD), ("szInfo", wintypes.WCHAR * 256),
                ("uTimeoutOrVersion", wintypes.UINT), ("szInfoTitle", wintypes.WCHAR * 64),
                ("dwInfoFlags", wintypes.DWORD), ("guidItem", ctypes.c_byte * 16),
                ("hBalloonIcon", wintypes.HICON)
            ]

        self.NOTIFYICONDATAW = NOTIFYICONDATAW
        self.user32.CreateWindowExW.restype = wintypes.HWND
        self.user32.CreatePopupMenu.restype = wintypes.HMENU
        self.user32.LoadImageW.restype = wintypes.HANDLE
        self.user32.LoadIconW.restype = wintypes.HICON
        self.user32.TrackPopupMenu.restype = wintypes.UINT
        kernel32 = ctypes.windll.kernel32
        kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE
        instance = kernel32.GetModuleHandleW(None)

        def wnd_proc(hwnd, message, wparam, lparam):
            if message == self.WM_TRAY:
                if lparam == self.WM_LBUTTONDBLCLK:
                    self._open_monitor()
                elif lparam == self.WM_RBUTTONUP:
                    self._show_menu(hwnd)
                return 0
            if message == self.WM_COMMAND:
                command = wparam & 0xffff
                if command == self.OPEN:
                    self._open_monitor()
                elif command == self.DASHBOARD:
                    webbrowser.open(self.app_controller.dashboard_url(), new=1)
                elif command == self.EXIT:
                    exit_requested.set()
                return 0
            if message == self.WM_CLOSE:
                self.user32.DestroyWindow(hwnd)
                return 0
            if message == self.WM_DESTROY:
                self._remove_icon(hwnd)
                self.user32.PostQuitMessage(0)
                return 0
            return self.user32.DefWindowProcW(hwnd, message, wparam, lparam)

        self.callback = WNDPROC(wnd_proc)
        wc = WNDCLASSW()
        wc.lpfnWndProc = self.callback
        wc.hInstance = instance
        wc.lpszClassName = self.class_name
        self.user32.RegisterClassW(ctypes.byref(wc))
        self.hwnd = self.user32.CreateWindowExW(0, self.class_name, "TTS Studio Tray", 0,
                                                0, 0, 0, 0, ctypes.c_void_p(-3), None, instance, None)
        if not self.hwnd:
            raise ctypes.WinError()
        self.icon = self.user32.LoadImageW(None, ICON_FILE, 1, 0, 0, 0x0010 | 0x0040)
        if not self.icon:
            self.icon = self.user32.LoadIconW(None, ctypes.c_void_p(32512))
        data = NOTIFYICONDATAW()
        data.cbSize = ctypes.sizeof(data)
        data.hWnd = self.hwnd
        data.uID = 1
        data.uFlags = 0x0001 | 0x0002 | 0x0004
        data.uCallbackMessage = self.WM_TRAY
        data.hIcon = self.icon
        data.szTip = "TTS Studio"
        if not self.shell32.Shell_NotifyIconW(0, ctypes.byref(data)):
            raise ctypes.WinError()

    def _remove_icon(self, hwnd):
        data = self.NOTIFYICONDATAW()
        data.cbSize = ctypes.sizeof(data)
        data.hWnd = hwnd
        data.uID = 1
        self.shell32.Shell_NotifyIconW(2, ctypes.byref(data))

    def _show_menu(self, hwnd):
        menu = self.user32.CreatePopupMenu()
        self.user32.AppendMenuW(menu, 0, self.OPEN, "Открыть монитор")
        self.user32.AppendMenuW(menu, 0x0800, 0, None)
        self.user32.AppendMenuW(menu, 0, self.DASHBOARD, "Открыть Dashboard")
        self.user32.AppendMenuW(menu, 0x0800, 0, None)
        self.user32.AppendMenuW(menu, 0, self.EXIT, "Выход")
        point = wintypes.POINT()
        self.user32.GetCursorPos(ctypes.byref(point))
        self.user32.SetForegroundWindow(hwnd)
        command = self.user32.TrackPopupMenu(menu, 0x0100, point.x, point.y, 0, hwnd, None)
        self.user32.DestroyMenu(menu)
        if command:
            self.user32.PostMessageW(hwnd, self.WM_COMMAND, command, 0)

    def _open_monitor(self):
        webbrowser.open(self.monitor_url, new=2)


def backend_address():
    config_path = os.path.join(SERVER_DIR, "config.json")
    try:
        with open(config_path, "r", encoding="utf-8") as stream:
            config = json.load(stream)
    except (OSError, ValueError):
        config = {}
    if not isinstance(config, dict):
        config = {}
    host = str(config.get("host", "127.0.0.1")).strip() or "127.0.0.1"
    try:
        port = int(config.get("port", 8765))
    except (TypeError, ValueError):
        port = 8765
    if not 1 <= port <= 65535:
        port = 8765
    if host == "0.0.0.0":
        host = "127.0.0.1"
    elif host == "::":
        host = "::1"
    url_host = "[{}]".format(host) if ":" in host and not host.startswith("[") else host
    return host, port, "http://{}:{}".format(url_host, port)


def acquire_singleton():
    global _singleton_handle
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    _singleton_handle = kernel32.CreateMutexW(None, True, "Local\\StreamTTSStudioLauncher")
    if not _singleton_handle:
        raise ctypes.WinError()
    if kernel32.GetLastError() == 183:
        ctypes.windll.user32.MessageBoxW(
            None, "TTS Studio уже запущена. Откройте монитор через значок в системном трее.",
            "TTS Studio", 0x40
        )
        return False
    return True


def main():
    global controller
    if not acquire_singleton():
        return
    for required, message in (
        (PYTHON_EXE, "Не найден portable python.exe: {}"),
        (APP_FILE, "Не найден backend: {}"),
        (ICON_FILE, "Не найдена иконка приложения: {}")
    ):
        if not os.path.isfile(required):
            raise FileNotFoundError(message.format(required))

    with open(LOG_FILE, "w", encoding="utf-8", buffering=1) as log_stream:
        log_stream.write("[{}] Запуск TTS Studio Monitor\n".format(datetime.now().astimezone().isoformat(timespec="seconds")))
        log_stream.write("Python: {}\n".format(PYTHON_EXE))
        log_stream.write("Entry point: {}\n".format(APP_FILE))
        http_server = ThreadingHTTPServer(("127.0.0.1", 0), MonitorLauncherHandler)
        http_server.daemon_threads = True
        monitor_port = http_server.server_address[1]
        threading.Thread(target=http_server.serve_forever, name="monitor-launcher-http", daemon=True).start()
        monitor_url = "http://127.0.0.1:{}/?launcher=1".format(monitor_port)
        _, _, backend_url = backend_address()
        controller = LauncherController(backend_url, monitor_port, log_stream)
        tray = Win32TrayIcon(monitor_url, controller)
        try:
            tray.start()
            webbrowser.open(monitor_url, new=2)
            controller.write_log("Монитор открыт в браузере по умолчанию.")
            controller.start_backend()
            while not exit_requested.wait(0.5):
                controller.refresh()
        finally:
            controller.write_log("Завершение launcher.")
            controller.stop_backend()
            http_server.shutdown()
            http_server.server_close()
            tray.stop()


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        error_text = traceback.format_exc()
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as stream:
                stream.write(error_text + "\n")
                stream.flush()
        except OSError:
            pass
        try:
            ctypes.windll.user32.MessageBoxW(
                None, "Не удалось запустить TTS Studio.\nПодробности: {}".format(LOG_FILE),
                "TTS Studio — ошибка запуска", 0x10
            )
        except Exception:
            pass
        raise
