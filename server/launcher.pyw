# -*- coding: utf-8 -*-
"""Start the monitor UI first, then launch the TTS backend with visible diagnostics."""
import ctypes
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
from urllib.parse import urlsplit

SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SERVER_DIR)
WEB_DIR = os.path.join(BASE_DIR, "web", "monitor")
LOG_DIR = os.path.join(BASE_DIR, "logs")
LOG_FILE = os.path.join(LOG_DIR, "startup.log")
APP_FILE = os.path.join(SERVER_DIR, "app.py")
PYTHON_EXE = os.path.join(BASE_DIR, "cosyvoice3", "upy", "python.exe")

os.makedirs(LOG_DIR, exist_ok=True)
state = {"status": "starting", "backend_url": "", "detail": "", "pid": None, "exit_code": None}
state_lock = threading.Lock()


def update_state(**values):
    with state_lock:
        state.update(values)


class MonitorLauncherHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        client_ip = self.client_address[0]
        host_header = self.headers.get("Host", "").split(":", 1)[0].strip("[]").lower()
        if client_ip not in ("127.0.0.1", "::1") or host_header not in ("127.0.0.1", "localhost"):
            self.send_error(403)
            return

        path = urlsplit(self.path).path
        if path == "/launcher-status":
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
        asset = assets.get(path)
        if asset is None:
            self.send_error(404)
            return
        try:
            with open(os.path.join(WEB_DIR, asset[0]), "rb") as stream:
                payload = stream.read()
        except OSError:
            self.send_error(404)
            return
        self._send(200, asset[1], payload)

    def _send(self, status, content_type, payload):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format_string, *args):
        return


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


def open_monitor_window(url):
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


def main():
    if not os.path.isfile(PYTHON_EXE):
        raise FileNotFoundError("Не найден portable python.exe: {}".format(PYTHON_EXE))
    if not os.path.isfile(APP_FILE):
        raise FileNotFoundError("Не найден backend: {}".format(APP_FILE))

    with open(LOG_FILE, "w", encoding="utf-8", buffering=1) as log_stream:
        log_stream.write("[{}] Запуск TTS Studio Monitor\n".format(datetime.now().astimezone().isoformat(timespec="seconds")))
        log_stream.write("Python: {}\n".format(PYTHON_EXE))
        log_stream.write("Entry point: {}\n".format(APP_FILE))

        http_server = ThreadingHTTPServer(("127.0.0.1", 0), MonitorLauncherHandler)
        http_server.daemon_threads = True
        monitor_port = http_server.server_address[1]
        threading.Thread(target=http_server.serve_forever, name="monitor-launcher-http", daemon=True).start()
        monitor_url = "http://127.0.0.1:{}/?launcher=1".format(monitor_port)

        open_monitor_window(monitor_url)
        log_stream.write("[{}] Окно монитора открыто, запускаю backend.\n".format(datetime.now().astimezone().isoformat(timespec="seconds")))

        host, port, backend_url = backend_address()
        update_state(status="starting", backend_url=backend_url)
        child_env = os.environ.copy()
        child_env["STUDIO_MONITOR_MODE"] = "1"
        child_env["STUDIO_MONITOR_ORIGIN"] = "http://127.0.0.1:{}".format(monitor_port)
        child_env["PYTHONUNBUFFERED"] = "1"
        child = subprocess.Popen(
            [PYTHON_EXE, "-u", APP_FILE],
            cwd=BASE_DIR,
            env=child_env,
            stdout=log_stream,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        update_state(pid=child.pid)

        ready = False
        while child.poll() is None:
            if not ready:
                try:
                    with urllib.request.urlopen(backend_url + "/monitor", timeout=1) as response:
                        if response.status == 200:
                            ready = True
                            update_state(status="ready", detail="Backend готов")
                except Exception:
                    pass
            time.sleep(0.5)

        exit_code = child.returncode
        if exit_code == 0:
            update_state(status="stopped", detail="Студия завершила работу", exit_code=exit_code)
        else:
            update_state(status="error", detail="Backend завершился с кодом {}".format(exit_code), exit_code=exit_code)
        log_stream.write("[{}] Backend завершён, код: {}\n".format(datetime.now().astimezone().isoformat(timespec="seconds"), exit_code))
        log_stream.flush()

        # Keep the local diagnostics page available briefly after shutdown or startup failure.
        time.sleep(30 if ready else 120)
        http_server.shutdown()
        http_server.server_close()


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
                None,
                "Не удалось запустить TTS Studio.\nПодробности: {}".format(LOG_FILE),
                "TTS Studio — ошибка запуска",
                0x10
            )
        except Exception:
            pass
        raise
