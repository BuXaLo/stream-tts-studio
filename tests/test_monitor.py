import logging

from studio.core.monitor import EventHub, MonitorLogHandler


def test_event_hub_keeps_history_and_delivers_events():
    hub = EventHub(history_size=2)
    subscriber = hub.subscribe()
    hub.publish({"type": "generation", "status": "started"})
    hub.publish({"type": "generation", "status": "complete"})
    hub.publish({"type": "log", "level": "info"})
    assert len(hub.history()) == 2
    assert subscriber.get_nowait()["status"] == "started"
    hub.unsubscribe(subscriber)


def test_log_handler_publishes_structured_log_event(monkeypatch):
    from studio.core import monitor
    test_hub = EventHub()
    monkeypatch.setattr(monitor, "hub", test_hub)
    handler = MonitorLogHandler()
    record = logging.LogRecord("studio.test", logging.WARNING, __file__, 1, "warning %s", ("event",), None)
    handler.emit(record)
    event = test_hub.history()[-1]
    assert event["type"] == "log"
    assert event["level"] == "warning"
    assert event["message"] == "warning event"



def test_install_monitor_log_handler_captures_non_propagating_studio_logger(monkeypatch):
    from studio.core import monitor

    test_hub = EventHub()
    monkeypatch.setattr(monitor, "hub", test_hub)
    studio_logger = logging.getLogger("studio.test_monitor_capture")
    previous_propagate = studio_logger.propagate
    handler = monitor.install_monitor_log_handler(studio_logger)
    studio_logger.propagate = False
    try:
        studio_logger.warning("studio logger warning")
        events = test_hub.history()
        assert len(events) == 1
        assert events[0]["type"] == "log"
        assert events[0]["level"] == "warning"
        assert events[0]["message"] == "studio logger warning"
    finally:
        studio_logger.removeHandler(handler)
        logging.getLogger().removeHandler(handler)
        studio_logger.propagate = previous_propagate
