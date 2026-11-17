"""Durable, deterministic JSON records with atomic writes."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def stable_id(prefix: str, *parts: str) -> str:
    canonical = "\x1f".join(str(x) for x in parts).encode("utf-8")
    return prefix + "-" + hashlib.sha256(canonical).hexdigest()[:18]


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def atomic_bytes(path: str | Path, data: bytes) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="." + p.name + ".", dir=str(p.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def atomic_json(path: str | Path, value: Any) -> None:
    atomic_bytes(path, json_bytes(value))


def atomic_jsonl(path: str | Path, records: list[dict]) -> None:
    data = ("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in records)).encode("utf-8")
    atomic_bytes(path, data)


def read_json(path: str | Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def read_jsonl(path: str | Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(s) for s in f if s.strip()]
