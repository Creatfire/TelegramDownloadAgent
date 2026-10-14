"""Activity log + event bus: records system/download events and pushes live updates to the console (SSE)."""
from __future__ import annotations

import asyncio
import itertools
import json
import time
from collections import deque
from typing import Any

from .config import ACTIVITY_FILE

_MAX_MEMORY = 500
_MAX_FILE_BYTES = 5 * 1024 * 1024


class EventBus:
    def __init__(self) -> None:
        self._seq = itertools.count(1)
        self.recent: deque[dict[str, Any]] = deque(maxlen=_MAX_MEMORY)
        self._subscribers: set[asyncio.Queue] = set()
        self._load_tail()

    def _load_tail(self) -> None:
        if not ACTIVITY_FILE.exists():
            return
        try:
            # update() appends a new line for the same id; keep the latest per id
            by_id: dict[int, dict[str, Any]] = {}
            for line in ACTIVITY_FILE.read_text("utf-8").splitlines()[-_MAX_MEMORY * 2:]:
                ev = json.loads(line)
                by_id[ev.get("id", 0)] = ev
            for ev in sorted(by_id.values(), key=lambda e: e.get("id", 0))[-_MAX_MEMORY:]:
                self.recent.append(ev)
            if self.recent:
                self._seq = itertools.count(self.recent[-1].get("id", 0) + 1)
        except Exception:
            pass

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    def _push(self, kind: str, payload: dict[str, Any]) -> None:
        for q in list(self._subscribers):
            try:
                q.put_nowait({"kind": kind, "data": payload})
            except asyncio.QueueFull:
                pass

    def log(self, level: str, source: str, title: str, detail: str = "", **extra: Any) -> dict[str, Any]:
        """level: info / success / warn / error; source: who caused it (agent name, system, download…)."""
        ev = {
            "id": next(self._seq),
            "ts": time.time(),
            "level": level,
            "source": source,
            "title": title,
            "detail": detail,
            **extra,
        }
        self.recent.append(ev)
        self._persist(ev)
        self._push("activity", ev)
        return ev

    def update(self, ev: dict[str, Any], **changes: Any) -> None:
        """Update an event that was already published."""
        ev.update(changes)
        self._persist(ev)
        self._push("activity", ev)

    def emit(self, kind: str, payload: dict[str, Any]) -> None:
        """Transient event (not persisted), e.g. progress snapshots."""
        self._push(kind, payload)

    def _persist(self, ev: dict[str, Any]) -> None:
        try:
            if ACTIVITY_FILE.exists() and ACTIVITY_FILE.stat().st_size > _MAX_FILE_BYTES:
                lines = ACTIVITY_FILE.read_text("utf-8").splitlines()[-_MAX_MEMORY:]
                ACTIVITY_FILE.write_text("\n".join(lines) + "\n", "utf-8")
            with ACTIVITY_FILE.open("a", encoding="utf-8") as f:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        except Exception:
            pass


bus = EventBus()
