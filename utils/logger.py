"""
logger.py — Structured event logging to JSONL + in-memory ring buffer.

Every state transition and alert is written as a JSON line to logs/session.jsonl.
The in-memory deque (capped at MAX_EVENTS_IN_MEMORY) feeds the /events endpoint
without reading from disk on every request.
"""

import json
import time
import threading
import os
from collections import deque

import config


class EventLogger:
    """
    Thread-safe event logger.

    Usage:
        logger = EventLogger()
        logger.log("state_change", state.to_dict())
        events = logger.recent()
    """

    def __init__(self):
        self._lock   = threading.Lock()
        self._buffer: deque[dict] = deque(maxlen=config.MAX_EVENTS_IN_MEMORY)
        self._last_status = "NORMAL"
        os.makedirs(config.LOG_DIR, exist_ok=True)

    def check_and_log(self, state_dict: dict) -> None:
        """
        Compare current status to last logged status.
        Log whenever status transitions OR a head drop occurs.
        """
        current_status = state_dict.get("status", "NORMAL")
        head_drops     = state_dict.get("head_drops", 0)

        should_log = (
            current_status != self._last_status or
            state_dict.get("no_face") or
            head_drops > 0
        )

        if should_log:
            event_type = (
                "state_transition" if current_status != self._last_status
                else "head_drop"   if head_drops > 0
                else "no_face"
            )
            self._last_status = current_status
            self.log(event_type, state_dict)

    def log(self, event_type: str, payload: dict) -> None:
        """Write a single event to memory buffer and disk."""
        entry = {
            "timestamp":  time.strftime("%H:%M:%S"),
            "unix_time":  round(time.time(), 2),
            "event_type": event_type,
            **payload,
        }
        with self._lock:
            self._buffer.appendleft(entry)   # newest first
            self._write_to_disk(entry)

    def recent(self, n: int = 50) -> list[dict]:
        """Return the N most recent events (newest first)."""
        with self._lock:
            return list(self._buffer)[:n]

    def _write_to_disk(self, entry: dict) -> None:
        try:
            with open(config.LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError:
            pass
