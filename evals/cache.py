"""Disk cache for eval runs, so an unchanged case never costs twice.

A result is stored under a hash of everything that could change it: the prompt,
the tool definitions, the model, the question, the agent's code, and its docs. Change any
of those and the hash changes, so stale results are never replayed. Changing only a
CHECK does not change the hash, so re-scoring old answers is free."""
import hashlib
import json
import os
from pathlib import Path


def _dir() -> Path:
    return Path(os.getenv("EVAL_CACHE_DIR", "runs/cache"))


def key(*parts) -> str:
    blob = json.dumps(parts, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:24]


def fingerprint(paths: list[Path]) -> str:
    """Hash of file contents, so editing a doc or a line of agent code invalidates the cache."""
    h = hashlib.sha256()
    for p in sorted(paths):
        h.update(str(p).encode())
        h.update(p.read_bytes())
    return h.hexdigest()[:24]


def get(k: str):
    path = _dir() / f"{k}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def put(k: str, value) -> None:
    _dir().mkdir(parents=True, exist_ok=True)
    (_dir() / f"{k}.json").write_text(json.dumps(value), encoding="utf-8")
