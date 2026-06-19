"""
exporter.py — CSV export utility for session event logs.

Called by the /export route in app.py. Reads from logs/session.jsonl
and returns a CSV string (or file-like object) that Flask can send
as a downloadable attachment.
"""

import csv
import io
import json
import os

import config


EXPORT_FIELDS = [
    "timestamp", "event_type", "status", "fatigue_score",
    "ear", "mar", "yaw", "pitch", "roll",
    "blinks", "yawns", "head_drops", "alerts_fired",
]


def build_csv_from_log() -> str:
    """
    Read logs/session.jsonl and return its contents as a CSV string.
    Each line in the JSONL becomes one CSV row.
    """
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=EXPORT_FIELDS,
        extrasaction="ignore",
        lineterminator="\n",
    )
    writer.writeheader()

    if not os.path.exists(config.LOG_FILE):
        return output.getvalue()

    with open(config.LOG_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                writer.writerow(entry)
            except (json.JSONDecodeError, ValueError):
                continue

    return output.getvalue()


def build_csv_from_events(events: list[dict]) -> str:
    """
    Build a CSV string from the in-memory events list
    (used when no log file exists yet, e.g. during testing).
    """
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=EXPORT_FIELDS,
        extrasaction="ignore",
        lineterminator="\n",
    )
    writer.writeheader()
    for event in reversed(events):   # oldest first in export
        writer.writerow(event)
    return output.getvalue()