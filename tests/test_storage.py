import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from studio.core.storage import StorageError, get_file_lock, read_json, write_json_atomic


def test_atomic_write_keeps_previous_valid_generation(tmp_path):
    path = tmp_path / "presets.json"
    write_json_atomic(path, {"first": 1})
    write_json_atomic(path, {"second": 2})
    assert json.loads(path.read_text(encoding="utf-8")) == {"second": 2}
    assert json.loads((tmp_path / "presets.json.bak").read_text(encoding="utf-8")) == {"first": 1}


def test_corrupt_file_recovers_from_backup_without_rewriting(tmp_path):
    path = tmp_path / "presets.json"
    path.write_text("{broken", encoding="utf-8")
    (tmp_path / "presets.json.bak").write_text('{"kept": true}', encoding="utf-8")
    assert read_json(path, {}, strict=True) == {"kept": True}
    assert path.read_text(encoding="utf-8") == "{broken"


def test_required_corrupt_file_raises_storage_error(tmp_path):
    path = tmp_path / "presets.json"
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(StorageError):
        read_json(path, {}, strict=True)


def test_failed_replace_preserves_original_file(tmp_path, monkeypatch):
    path = tmp_path / "presets.json"
    path.write_text('{"safe": true}', encoding="utf-8")
    import studio.core.storage as storage
    original_replace = storage.os.replace

    def fail_main_replace(source, destination):
        if str(destination) == str(path):
            raise OSError("simulated disk failure")
        return original_replace(source, destination)

    monkeypatch.setattr(storage.os, "replace", fail_main_replace)
    with pytest.raises(OSError):
        write_json_atomic(path, {"unsafe": True})
    assert json.loads(path.read_text(encoding="utf-8")) == {"safe": True}


def test_concurrent_atomic_writes_always_leave_valid_json(tmp_path):
    path = tmp_path / "presets.json"
    write_json_atomic(path, {"initial": True})
    stop = threading.Event()
    failures = []

    def reader():
        while not stop.is_set():
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                failures.append(exc)
                stop.set()

    thread = threading.Thread(target=reader)
    thread.start()
    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda i: write_json_atomic(path, {"value": i}), range(100)))
    finally:
        stop.set()
        thread.join()
    assert not failures
    assert isinstance(json.loads(path.read_text(encoding="utf-8")), dict)


def test_missing_main_file_recovers_from_backup(tmp_path):
    path = tmp_path / "presets.json"
    (tmp_path / "presets.json.bak").write_text('{"recovered": true}', encoding="utf-8")
    assert read_json(path, {}, strict=True) == {"recovered": True}

def test_file_lock_prevents_lost_updates(tmp_path):
    path = tmp_path / "presets.json"
    write_json_atomic(path, {"count": 0})
    lock = get_file_lock(path)

    def increment(_):
        with lock:
            data = read_json(path, {})
            data["count"] += 1
            write_json_atomic(path, data)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(increment, range(160)))

    assert read_json(path, {})["count"] == 160
