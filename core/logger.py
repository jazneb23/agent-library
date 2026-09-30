"""Append only JSON lines log. One line per event. This is the audit trail:
you can reconstruct exactly what the agent did, in order, and what it cost."""
import json
import os
import time

from core import config


def log_event(run_id: str, event: str, **data) -> None:
    os.makedirs(os.path.dirname(config.LOG_PATH) or ".", exist_ok=True)
    record = {"ts": round(time.time(), 3), "run_id": run_id, "event": event, **data}
    with open(config.LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")
