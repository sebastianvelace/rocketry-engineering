"""Small, local event log shared by terminal agents and Streamlit."""
from __future__ import annotations

import json
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / ".console"
EVENTS_PATH = STATE_DIR / "agent-events.jsonl"
MAX_BYTES = 2_000_000


def emit(provider: str, event: str, message: str, *, data: dict[str, Any] | None = None) -> None:
    """Append one normalized event and keep the local log bounded."""
    STATE_DIR.mkdir(exist_ok=True)
    if EVENTS_PATH.exists() and EVENTS_PATH.stat().st_size > MAX_BYTES:
        recent = read_events(250)
        EVENTS_PATH.write_text(
            "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in recent),
            encoding="utf-8",
        )
    payload = {
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "provider": provider,
        "event": event,
        "message": message,
        "data": data or {},
    }
    with EVENTS_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def read_events(limit: int = 80) -> list[dict[str, Any]]:
    """Read only the tail of the feed; malformed partial lines are ignored."""
    if not EVENTS_PATH.exists():
        return []
    with EVENTS_PATH.open(encoding="utf-8") as handle:
        lines = deque(handle, maxlen=limit)
    events = []
    for line in lines:
        try:
            events.append(json.loads(line))
        except (json.JSONDecodeError, TypeError):
            continue
    return events
