# -*- coding: utf-8 -*-
"""Monitor launcher with a persistent Windows notification-area icon."""
import ctypes
from ctypes import wintypes
import json
import os
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SERVER_DIR)
WEB_DIR = os.path.join(BASE_DIR, "web", "monitor")
ICON_FILE = os.path.join(BASE_DIR, "web", "dashboard", "favicon.ico")
LOG_DIR = os.path.join(BASE_DIR, "logs")
LOG_FILE = os.path.join(LOG_DIR, "startup.log")
APP_FILE = os.path.join(SERVER_DIR, "app.py")
PYTHON_EXE = os.path.join(BASE_DIR, "cosyvoice3", "upy", "python.exe")

# Собственное окно монитора (pywebview + WebView2). Если оно недоступно,
# launcher работает как раньше: Edge с --app=, иначе браузер по умолчанию.
MONITOR_WINDOW_ENV = "STUDIO_MONITOR_WINDOW"  # значение "browser" отключает pywebview
WINDOW_TITLE = "TTS Studio — Монитор"
WINDOW_BACKGROUND = "#0b0d12"
WINDOW_LOAD_TIMEOUT = 25  # секунд на первую загрузку страницы монитора
WINDOW_EXIT_GRACE = 20    # секунд на закрытие окна при выходе
APP_USER_MODEL_ID = "StreamTTSStudio.Monitor"
WEBVIEW2_CLIENT_GUID = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
os.makedirs(LOG_DIR, exist_ok=True)

state = {"status": "starting", "backend_url": "", "detail": "", "pid": None, "exit_code": None}
state_lock = threading.RLock()
exit_requested = threading.Event()
controller = None
monitor_window = None
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
            child_env["PYTHONIOENCODING"] = "utf-8"
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
        return self.backend_url + "/dashboard/"

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
                status = dict(state)
            status["close_monitor"] = exit_requested.is_set()
            payload = json.dumps(status, ensure_ascii=False).encode("utf-8")
            self._send(200, "application/json; charset=utf-8", payload)
            return
        if path == "/startup-log":
            query = parse_qs(urlsplit(self.path).query)
            if "offset" not in query:
                try:
                    with open(LOG_FILE, "rb") as stream:
                        stream.seek(0, os.SEEK_END)
                        position = stream.tell()
                        chunks = []
                        decoded_content = ""
                        while position > 0 and len(decoded_content) <= 131072:
                            chunk_size = min(65536, position)
                            position -= chunk_size
                            stream.seek(position)
                            chunks.insert(0, stream.read(chunk_size))
                            decoded_content = b"".join(chunks).decode("utf-8", errors="replace")
                        content = decoded_content[max(0, len(decoded_content) - 131072):]
                except OSError:
                    content = ""
                self._send(200, "text/plain; charset=utf-8", content.encode("utf-8"))
                return
            try:
                offset = int(query["offset"][0])
                if offset < 0:
                    raise ValueError
            except (IndexError, ValueError):
                self.send_error(400, "Invalid log offset")
                return
            try:
                with open(LOG_FILE, "rb") as stream:
                    size = os.fstat(stream.fileno()).st_size
                    if offset > size:
                        offset = 0
                    stream.seek(offset)
                    payload = stream.read()
                    new_offset = stream.tell()
            except OSError:
                payload = b""
                new_offset = 0
            self._send(
                200,
                "text/plain; charset=utf-8",
                payload,
                headers={"X-Log-Offset": str(new_offset)},
            )
            return
        assets = {
            "/": ("index.html", "text/html; charset=utf-8"),
            "/monitor": ("index.html", "text/html; charset=utf-8"),
            "/monitor/": ("index.html", "text/html; charset=utf-8"),
            "/monitor/index.html": ("index.html", "text/html; charset=utf-8"),
            "/monitor/app.js": ("app.js", "application/javascript; charset=utf-8"),
            "/monitor/style.css": ("style.css", "text/css; charset=utf-8"),
            "/manifest.webmanifest": (
                "manifest.webmanifest",
                "application/manifest+json; charset=utf-8",
            ),
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
        if path == "/launcher-stop":
            try:
                controller.stop_backend()
                self._send(200, "application/json; charset=utf-8", b'{"status":"stopped"}')
            except Exception as exc:
                controller.write_log("Ошибка выключения backend: {}".format(traceback.format_exc()))
                payload = json.dumps({"detail": str(exc)}, ensure_ascii=False).encode("utf-8")
                self._send(500, "application/json; charset=utf-8", payload)
            return
        if path == "/open-dashboard":
            opened = webbrowser.open(controller.dashboard_url(), new=1)
            payload = json.dumps({"opened": bool(opened)}).encode("utf-8")
            self._send(200 if opened else 500, "application/json; charset=utf-8", payload)
            return
        self.send_error(404)

    def _send(self, status, content_type, payload, headers=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
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
            if not self.user32.PostMessageW(self.hwnd, self.WM_CLOSE, 0, 0):
                self.app_controller.write_log(
                    "Не удалось отправить WM_CLOSE окну системного трея: {}".format(ctypes.WinError())
                )
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
        try:
            message = wintypes.MSG()
            while True:
                result = self.user32.GetMessageW(ctypes.byref(message), None, 0, 0)
                if result == -1:
                    raise ctypes.WinError()
                if result == 0:
                    break
                self.user32.TranslateMessage(ctypes.byref(message))
                self.user32.DispatchMessageW(ctypes.byref(message))
        except Exception:
            self.error = traceback.format_exc()
            self.app_controller.write_log(
                "Ошибка цикла сообщений системного трея:\n{}".format(self.error)
            )
            exit_requested.set()

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
        user32 = self.user32
        kernel32 = ctypes.windll.kernel32

        # Явные сигнатуры обязательны: без них ctypes может обрезать
        # 64-битные HWND/HINSTANCE при передаче дескрипторов.
        user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
        user32.RegisterClassW.restype = wintypes.ATOM
        user32.CreateWindowExW.argtypes = [
            wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID
        ]
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.DefWindowProcW.argtypes = [
            wintypes.HWND, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t
        ]
        user32.DefWindowProcW.restype = ctypes.c_ssize_t
        user32.DestroyWindow.argtypes = [wintypes.HWND]
        user32.DestroyWindow.restype = wintypes.BOOL
        user32.PostMessageW.argtypes = [
            wintypes.HWND, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t
        ]
        user32.PostMessageW.restype = wintypes.BOOL
        user32.PostQuitMessage.argtypes = [ctypes.c_int]
        user32.PostQuitMessage.restype = None
        user32.GetMessageW.argtypes = [
            ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT
        ]
        user32.GetMessageW.restype = wintypes.BOOL
        user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user32.TranslateMessage.restype = wintypes.BOOL
        user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user32.DispatchMessageW.restype = ctypes.c_ssize_t
        user32.CreatePopupMenu.argtypes = []
        user32.CreatePopupMenu.restype = wintypes.HMENU
        user32.AppendMenuW.argtypes = [
            wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR
        ]
        user32.AppendMenuW.restype = wintypes.BOOL
        user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
        user32.GetCursorPos.restype = wintypes.BOOL
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        user32.SetForegroundWindow.restype = wintypes.BOOL
        user32.TrackPopupMenu.argtypes = [
            wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int,
            ctypes.c_int, wintypes.HWND, wintypes.LPVOID
        ]
        user32.TrackPopupMenu.restype = wintypes.UINT
        user32.DestroyMenu.argtypes = [wintypes.HMENU]
        user32.DestroyMenu.restype = wintypes.BOOL
        user32.LoadImageW.argtypes = [
            wintypes.HANDLE, wintypes.LPCWSTR, wintypes.UINT,
            ctypes.c_int, ctypes.c_int, wintypes.UINT
        ]
        user32.LoadImageW.restype = wintypes.HANDLE
        self.shell32.Shell_NotifyIconW.argtypes = [
            wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)
        ]
        self.shell32.Shell_NotifyIconW.restype = wintypes.BOOL
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE
        instance = kernel32.GetModuleHandleW(None)
        if not instance:
            raise ctypes.WinError()

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
        if not self.user32.RegisterClassW(ctypes.byref(wc)):
            raise ctypes.WinError()
        self.hwnd = self.user32.CreateWindowExW(
            0, self.class_name, "TTS Studio Tray", 0,
            0, 0, 0, 0, wintypes.HWND(-3), None, instance, None
        )
        if not self.hwnd:
            raise ctypes.WinError()
        self.icon = self.user32.LoadImageW(None, ICON_FILE, 1, 0, 0, 0x0010 | 0x0040)
        if not self.icon:
            raise ctypes.WinError()
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
        open_monitor_window(self.monitor_url)


def webview2_runtime_version():
    """Версия WebView2 Runtime из реестра (только чтение) или None."""
    try:
        import winreg
    except ImportError:
        return None
    candidates = (
        (winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\\WOW6432Node\\Microsoft\\EdgeUpdate\\Clients\\{}"),
        (winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\\Microsoft\\EdgeUpdate\\Clients\\{}"),
        (winreg.HKEY_CURRENT_USER, "Software\\Microsoft\\EdgeUpdate\\Clients\\{}"),
    )
    for root, template in candidates:
        try:
            with winreg.OpenKey(root, template.format(WEBVIEW2_CLIENT_GUID)) as key:
                value, _ = winreg.QueryValueEx(key, "pv")
        except OSError:
            continue
        value = str(value).strip()
        if value and value != "0.0.0.0":
            return value
    return None


def import_webview():
    """Ленивый импорт pywebview: (модуль, None) или (None, текст ошибки)."""
    try:
        import webview
        return webview, None
    except Exception:
        return None, traceback.format_exc()


def choose_monitor_mode(env_value, webview_available, runtime_version):
    """Возвращает (режим, причина); режим: "webview" или "browser"."""
    if str(env_value or "").strip().lower() == "browser":
        return "browser", "{}=browser".format(MONITOR_WINDOW_ENV)
    if not webview_available:
        return "browser", "пакет pywebview не импортируется"
    if not runtime_version:
        return "browser", "WebView2 Runtime не найден в реестре"
    return "webview", "pywebview + WebView2 {}".format(runtime_version)


def select_monitor_mode(log):
    env_value = os.environ.get(MONITOR_WINDOW_ENV, "")
    webview_module, import_error = (None, None)
    if str(env_value).strip().lower() != "browser":
        webview_module, import_error = import_webview()
    runtime_version = webview2_runtime_version() if webview_module is not None else None
    mode, reason = choose_monitor_mode(env_value, webview_module is not None, runtime_version)
    if import_error:
        log("Импорт pywebview не удался:\n{}".format(import_error))
    if mode == "webview":
        try:
            from importlib import metadata
            version = metadata.version("pywebview")
        except Exception:
            version = "?"
        log("Режим окна монитора: pywebview {} ({}).".format(version, reason))
    else:
        log("Режим окна монитора: Edge/браузер ({}).".format(reason))
    return mode, webview_module


def _user32():
    user32 = ctypes.windll.user32
    user32.LoadImageW.argtypes = [
        wintypes.HANDLE, wintypes.LPCWSTR, wintypes.UINT,
        ctypes.c_int, ctypes.c_int, wintypes.UINT
    ]
    user32.LoadImageW.restype = wintypes.HANDLE
    user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t]
    user32.SendMessageW.restype = ctypes.c_ssize_t
    user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    user32.GetSystemMetrics.restype = ctypes.c_int
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowW.restype = wintypes.HWND
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.IsIconic.restype = wintypes.BOOL
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    return user32


def set_app_user_model_id():
    """Чтобы в панели задач был значок студии, а не pythonw.exe."""
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(ctypes.c_wchar_p(APP_USER_MODEL_ID))
    except Exception:
        pass


def find_window_handle(window):
    """HWND окна pywebview: через window.native, запасной путь — по заголовку."""
    try:
        handle = window.native.Handle
        value = int(handle.ToInt64())
        if value:
            return value
    except Exception:
        pass
    try:
        return _user32().FindWindowW(None, WINDOW_TITLE) or None
    except Exception:
        return None


def apply_window_icon(hwnd):
    """Иконка окна из web/dashboard/favicon.ico (та же, что у трея)."""
    user32 = _user32()
    # (wParam для WM_SETICON, метрика ширины, метрика высоты): большая и малая иконки
    for icon_kind, cx_metric, cy_metric in ((1, 11, 12), (0, 49, 50)):
        icon = user32.LoadImageW(
            None, ICON_FILE, 1,
            user32.GetSystemMetrics(cx_metric), user32.GetSystemMetrics(cy_metric), 0x0010
        )
        if icon:
            user32.SendMessageW(hwnd, 0x0080, icon_kind, icon)


def bring_window_to_front(hwnd):
    user32 = _user32()
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.SetForegroundWindow(hwnd)


class MonitorWindow:
    """Окно монитора на pywebview. Один экземпляр на сеанс launcher.

    Крестик скрывает окно (backend продолжает работать), «Открыть монитор» в трее
    возвращает то же окно, «Выход» закрывает его по-настоящему.
    """

    def __init__(self, webview_module, url, log, open_fallback, force_exit):
        self.webview = webview_module
        self.url = url
        self.log = log
        self.open_fallback = open_fallback
        self.force_exit = force_exit
        self.window = None
        self.hwnd = None
        self.active = True
        self.loaded = threading.Event()
        self.finished = threading.Event()
        self.allow_close = threading.Event()
        self._fallback_done = False
        self._lock = threading.Lock()

    def run(self):
        """Блокирует главный поток до закрытия окна. Исключение значит сбой запуска."""
        set_app_user_model_id()
        try:
            self.window = self.webview.create_window(
                WINDOW_TITLE, url=self.url, width=1280, height=820, min_size=(900, 600),
                background_color=WINDOW_BACKGROUND, text_select=True
            )
            self.window.events.closing += self._on_closing
            self.window.events.loaded += self._on_loaded
            self.window.events.shown += self._on_shown
            threading.Thread(target=self._watch_exit, name="monitor-window-exit", daemon=True).start()
            threading.Thread(target=self._watch_load, name="monitor-window-load", daemon=True).start()
            # gui задан явно: иначе pywebview может молча уйти на старый движок MSHTML.
            self.webview.start(gui="edgechromium")
        finally:
            self.finished.set()

    def _on_loaded(self):
        self.loaded.set()

    def _on_shown(self):
        try:
            self.hwnd = find_window_handle(self.window)
            if self.hwnd:
                apply_window_icon(self.hwnd)
        except Exception as exc:
            self.log("Не удалось установить иконку окна монитора: {}".format(exc))

    def _on_closing(self):
        if self.allow_close.is_set() or exit_requested.is_set():
            return True
        self.log("Окно монитора скрыто (закрытие окна не останавливает backend).")
        # hide() вызываем вне обработчика события, чтобы не словить взаимную блокировку.
        threading.Thread(target=self._hide, name="monitor-window-hide", daemon=True).start()
        return False

    def _hide(self):
        try:
            self.window.hide()
        except Exception as exc:
            self.log("Не удалось скрыть окно монитора: {}".format(exc))

    def show(self):
        """Показать окно. False, если окна нет и нужен запасной режим."""
        if not self.active:
            return False
        if self.window is None or not self.loaded.is_set():
            return True  # окно ещё запускается и уже видно
        try:
            self.window.show()
            hwnd = self.hwnd or find_window_handle(self.window)
            if hwnd:
                bring_window_to_front(hwnd)
        except Exception as exc:
            self.log("Не удалось показать окно монитора: {}".format(exc))
            return False
        return True

    def destroy(self):
        self.allow_close.set()
        try:
            if self.window is not None:
                self.window.destroy()
        except Exception as exc:
            self.log("Не удалось закрыть окно монитора: {}".format(exc))

    def fallback(self):
        """Один раз открыть запасной монитор (Edge/браузер)."""
        with self._lock:
            if self._fallback_done:
                return
            self._fallback_done = True
            self.active = False
        self.open_fallback()

    def _watch_exit(self):
        exit_requested.wait()
        self.destroy()
        if not self.finished.wait(WINDOW_EXIT_GRACE):
            self.log("Окно монитора не закрылось за {} с. Принудительное завершение.".format(WINDOW_EXIT_GRACE))
            self.force_exit()

    def _watch_load(self):
        if self.loaded.wait(WINDOW_LOAD_TIMEOUT) or exit_requested.is_set() or self.finished.is_set():
            return
        self.log("Окно pywebview не загрузило монитор за {} с. Запасной режим.".format(WINDOW_LOAD_TIMEOUT))
        self.destroy()
        if not self.finished.wait(10):
            self.fallback()


def run_webview_monitor(webview_module, monitor_url, force_exit):
    """Окно pywebview в главном потоке. При сбое включает запасной монитор."""
    global monitor_window
    window = MonitorWindow(
        webview_module, monitor_url, controller.write_log,
        lambda: open_monitor_window(monitor_url), force_exit
    )
    monitor_window = window
    try:
        window.run()
    except Exception:
        controller.write_log("Ошибка окна pywebview:\n{}".format(traceback.format_exc()))
    finally:
        window.active = False
        monitor_window = None
    if exit_requested.is_set():
        return
    controller.write_log("Окно pywebview недоступно. Запасной режим: монитор в Edge/браузере.")
    window.fallback()


def supervise_until_exit():
    while not exit_requested.wait(0.5):
        controller.refresh()


def open_monitor_window(url):
    if monitor_window is not None and monitor_window.show():
        return
    edge_candidates = [
        os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(os.environ.get("PROGRAMFILES", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
    ]
    edge_path = next((path for path in edge_candidates if path and os.path.isfile(path)), None)
    if edge_path:
        try:
            subprocess.Popen(
                [edge_path, "--app=" + url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )
            return
        except OSError:
            pass
    webbrowser.open(url)


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
    user32 = ctypes.windll.user32
    kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.GetLastError.argtypes = []
    kernel32.GetLastError.restype = wintypes.DWORD
    user32.MessageBoxW.argtypes = [
        wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.UINT
    ]
    user32.MessageBoxW.restype = ctypes.c_int
    _singleton_handle = kernel32.CreateMutexW(None, True, "Local\\StreamTTSStudioLauncher")
    if not _singleton_handle:
        raise ctypes.WinError()
    if kernel32.GetLastError() == 183:
        user32.MessageBoxW(
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

    original_stdout, original_stderr = sys.stdout, sys.stderr
    with open(LOG_FILE, "w", encoding="utf-8", buffering=1) as log_stream:
        log_stream.write("[{}] Запуск TTS Studio Monitor\n".format(datetime.now().astimezone().isoformat(timespec="seconds")))
        # pythonw.exe работает без консоли: sys.stdout/sys.stderr равны None.
        if sys.stdout is None:
            sys.stdout = log_stream
        if sys.stderr is None:
            sys.stderr = log_stream
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

        def force_exit():
            # Аварийный путь: окно pywebview не закрылось, главный поток завис в GUI-цикле.
            try:
                controller.write_log("Принудительное завершение launcher.")
                controller.stop_backend()
                tray.stop()
            finally:
                os._exit(0)

        try:
            tray.start()
            window_mode, webview_module = select_monitor_mode(controller.write_log)
            try:
                controller.start_backend()
            except Exception as exc:
                controller.set_state(status="error", detail="Не удалось запустить backend: {}".format(exc))
                controller.write_log("Ошибка первоначального запуска backend: {}".format(exc))
            threading.Thread(target=supervise_until_exit, name="studio-supervisor", daemon=True).start()
            if window_mode == "webview":
                # Блокирует главный поток до закрытия окна; сбой включает запасной режим.
                run_webview_monitor(webview_module, monitor_url, force_exit)
            else:
                open_monitor_window(monitor_url)
                controller.write_log("Монитор открыт в окне Edge/браузера.")
            while not exit_requested.wait(0.5):
                pass
        finally:
            controller.write_log("Завершение launcher.")
            controller.stop_backend()
            http_server.shutdown()
            http_server.server_close()
            tray.stop()
            sys.stdout, sys.stderr = original_stdout, original_stderr


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
