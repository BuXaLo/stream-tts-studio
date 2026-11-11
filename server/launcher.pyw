# -*- coding: utf-8 -*-
"""Hidden-window entry point that preserves startup diagnostics."""
import os
import runpy
import sys
import traceback
from datetime import datetime

SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SERVER_DIR)
LOG_DIR = os.path.join(BASE_DIR, "logs")
LOG_FILE = os.path.join(LOG_DIR, "startup.log")
APP_FILE = os.path.join(SERVER_DIR, "app.py")

os.makedirs(LOG_DIR, exist_ok=True)
log_stream = open(LOG_FILE, "a", encoding="utf-8", buffering=1)
sys.stdout = log_stream
sys.stderr = log_stream
print("\n[{}] Запуск TTS Studio Monitor".format(datetime.now().astimezone().isoformat(timespec="seconds")))
print("Python: {}".format(sys.executable))
print("Entry point: {}".format(APP_FILE))

try:
    runpy.run_path(APP_FILE, run_name="__main__")
except BaseException as exc:
    traceback.print_exc(file=log_stream)
    log_stream.flush()
    if not (isinstance(exc, SystemExit) and exc.code in (None, 0)):
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                None,
                "Не удалось запустить TTS Studio.\nПодробности записаны в:\n{}".format(LOG_FILE),
                "TTS Studio — ошибка запуска",
                0x10
            )
        except Exception:
            pass
    raise
finally:
    log_stream.flush()
    log_stream.close()
