# -*- coding: utf-8 -*-
"""Atomic JSON persistence helpers for Stream TTS Studio."""
import copy
import json
import logging
import os
import shutil
import tempfile
import threading
import time


class StorageError(RuntimeError):
    """Raised when a required JSON document and its backup are unreadable."""


_logger = logging.getLogger(__name__)
_locks = {}
_locks_guard = threading.Lock()


def get_file_lock(path):
    """Return the process-local lock associated with a data file."""
    key = os.path.normcase(os.path.abspath(os.fspath(path)))
    with _locks_guard:
        lock = _locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _locks[key] = lock
        return lock


def _load_json(path):
    with open(path, "r", encoding="utf-8") as stream:
        return json.load(stream)


def read_json(path, default=None, *, strict=False):
    """Read JSON, falling back to one .bak generation without overwriting data."""
    path = os.fspath(path)
    if not os.path.exists(path):
        return copy.deepcopy(default)

    try:
        return _load_json(path)
    except (OSError, ValueError, TypeError) as primary_error:
        backup_path = path + ".bak"
        try:
            value = _load_json(backup_path)
        except (OSError, ValueError, TypeError) as backup_error:
            message = "JSON and backup are unreadable for {!r}: {}; backup: {}".format(
                path, primary_error, backup_error
            )
            if strict:
                raise StorageError(message) from primary_error
            _logger.warning("%s; using in-memory default without overwriting files", message)
            return copy.deepcopy(default)

        _logger.warning("Recovered JSON data from backup: %s", backup_path)
        return value


def _replace_with_retry(source, destination):
    last_error = None
    for attempt in range(3):
        try:
            os.replace(source, destination)
            return
        except PermissionError as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(0.05)
    raise last_error


def write_json_atomic(path, data):
    """Write UTF-8 JSON atomically and retain one previous valid generation."""
    path = os.fspath(path)
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)

    fd, temp_path = tempfile.mkstemp(prefix=".studio-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())

        # Preserve only a parseable previous version. A corrupt file must not
        # overwrite a known-good backup.
        if os.path.isfile(path):
            try:
                _load_json(path)
            except (OSError, ValueError, TypeError):
                pass
            else:
                backup_path = path + ".bak"
                backup_fd, backup_temp = tempfile.mkstemp(
                    prefix=".studio-backup-", suffix=".tmp", dir=directory
                )
                try:
                    with os.fdopen(backup_fd, "wb") as backup_stream:
                        with open(path, "rb") as source_stream:
                            shutil.copyfileobj(source_stream, backup_stream)
                        backup_stream.flush()
                        os.fsync(backup_stream.fileno())
                    _replace_with_retry(backup_temp, backup_path)
                finally:
                    if os.path.exists(backup_temp):
                        os.remove(backup_temp)

        _replace_with_retry(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
