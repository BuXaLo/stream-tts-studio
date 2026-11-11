"""In-process event hub for the local desktop monitor."""
import logging
import queue
import threading
from collections import deque
from datetime import datetime


class EventHub:
    def __init__(self, history_size=500, queue_size=250):
        self._history = deque(maxlen=history_size)
        self._queue_size = queue_size
        self._subscribers = set()
        self._sequence = 0
        self._lock = threading.RLock()

    @staticmethod
    def timestamp():
        return datetime.now().astimezone().isoformat(timespec="seconds")

    def publish(self, event):
        item = dict(event)
        item.setdefault("timestamp", self.timestamp())
        with self._lock:
            self._sequence += 1
            item["event_id"] = self._sequence
            self._history.append(item)
            subscribers = tuple(self._subscribers)
        for subscriber in subscribers:
            try:
                subscriber.put_nowait(item)
            except queue.Full:
                try:
                    subscriber.get_nowait()
                except queue.Empty:
                    pass
                try:
                    subscriber.put_nowait(item)
                except queue.Full:
                    pass

    def history(self):
        with self._lock:
            return list(self._history)

    def subscribe(self):
        subscriber = queue.Queue(maxsize=self._queue_size)
        with self._lock:
            self._subscribers.add(subscriber)
        return subscriber

    def unsubscribe(self, subscriber):
        with self._lock:
            self._subscribers.discard(subscriber)


hub = EventHub()
_shutdown_lock = threading.Lock()
_shutdown_callback = None
_shutdown_requested = False


def publish_generation(status, **fields):
    hub.publish({"type": "generation", "status": status, **fields})


def set_shutdown_callback(callback):
    global _shutdown_callback
    with _shutdown_lock:
        _shutdown_callback = callback


def schedule_shutdown():
    global _shutdown_requested
    with _shutdown_lock:
        callback = _shutdown_callback
        if _shutdown_requested or callback is None:
            return False
        _shutdown_requested = True
    hub.publish({"type": "shutdown", "message": "Студия завершает работу"})
    timer = threading.Timer(0.6, callback)
    timer.daemon = True
    timer.start()
    return True


class MonitorLogHandler(logging.Handler):
    def emit(self, record):
        try:
            message = record.getMessage()
            if len(message) > 4000:
                message = message[:4000] + "…"
            hub.publish({
                "type": "log",
                "level": "error" if record.levelno >= logging.ERROR else ("warning" if record.levelno >= logging.WARNING else "info"),
                "logger": record.name,
                "message": message,
                "timestamp": datetime.fromtimestamp(record.created).astimezone().isoformat(timespec="seconds")
            })
        except Exception:
            self.handleError(record)
