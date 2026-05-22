from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

CACHE_ROOT = Path(__file__).resolve().parent.parent / "storage" / "cache"


def _key(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def cache_path(db: str, payload: Any) -> Path:
    p = CACHE_ROOT / db
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{_key(payload)}.json"


def load(db: str, payload: Any) -> Any | None:
    fp = cache_path(db, payload)
    if not fp.exists():
        return None
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def save(db: str, payload: Any, data: Any) -> None:
    fp = cache_path(db, payload)
    try:
        fp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
