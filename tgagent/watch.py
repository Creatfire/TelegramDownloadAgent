"""Watches: poll chosen chats and automatically download new files that match a filter.
Watches created by an AI start disabled until the user approves them in the console."""
from __future__ import annotations

import asyncio
import time
import uuid

from . import readers
from .accounts import manager as accounts
from .activity import bus
from .db import db, dumps, loads
from .i18n import L

FILTER_KEYS = ("types", "name_contains", "extensions", "min_size_mb", "max_size_mb")
MIN_INTERVAL = 5


def _public(r: dict) -> dict:
    r = dict(r)
    r["filters"] = loads(r.get("filters"), {})
    r["enabled"] = bool(r["enabled"])
    r["pending_approval"] = bool(r["pending_approval"])
    return r


class WatchManager:
    def __init__(self) -> None:
        self._wake = asyncio.Event()
        self._checking: set[str] = set()

    def list(self) -> list[dict]:
        return [_public(r) for r in db.all("SELECT * FROM watches ORDER BY created DESC")]

    def get(self, wid: str) -> dict:
        r = db.one("SELECT * FROM watches WHERE id=?", (wid,))
        if not r:
            raise ValueError(L(f"订阅不存在: {wid}", f"No such watch: {wid}"))
        return _public(r)

    async def add(self, account: str | None, chat: str, source: str, filters: dict | None = None,
                  interval_min: int = 30, subdir: str = "", include_recent: int = 0) -> dict:
        acc, client = await accounts.client(account)
        entity = await readers.get_entity(client, chat)
        chat_id = readers.utils.get_peer_id(entity)
        latest = 0
        async for m in client.iter_messages(entity, limit=1):
            latest = m.id
        start_from = latest
        if include_recent > 0:  # also pick up the N most recent messages
            start_from = max(0, latest - int(include_recent))
        human = source == "console"
        row = {
            "id": uuid.uuid4().hex[:8], "account": acc.id, "chat": str(chat), "chat_id": chat_id,
            "chat_title": readers.chat_title(entity),
            "filters": dumps({k: v for k, v in (filters or {}).items() if k in FILTER_KEYS and v not in (None, "", [])}),
            "interval_min": max(MIN_INTERVAL, int(interval_min or 30)), "subdir": subdir or "",
            "enabled": 1 if human else 0, "pending_approval": 0 if human else 1,
            "last_message_id": start_from, "last_check": 0, "last_error": "", "downloaded": 0,
            "created": time.time(), "source": source,
        }
        db.upsert("watches", row)
        bus.log("warn" if not human else "info", source,
                L("新建订阅" + ("（待批准）" if not human else ""), "Watch created" + (" (awaiting approval)" if not human else "")),
                row["chat_title"], watch_id=row["id"])
        self._wake.set()
        out = _public(row)
        if not human:
            out["hint"] = L("订阅已创建但未启用，需要用户在控制台「订阅」页批准。",
                            "The watch is created but disabled until the user approves it on the console's Watches page.")
        return out

    def update(self, wid: str, **changes) -> dict:
        w = self.get(wid)
        allowed = {k: v for k, v in changes.items() if k in ("enabled", "interval_min", "subdir", "filters")}
        if "filters" in allowed:
            allowed["filters"] = dumps(allowed["filters"])
        if "interval_min" in allowed:
            allowed["interval_min"] = max(MIN_INTERVAL, int(allowed["interval_min"]))
        if "enabled" in allowed:
            allowed["enabled"] = int(bool(allowed["enabled"]))
        if changes.get("approve"):
            allowed.update({"enabled": 1, "pending_approval": 0})
        if allowed:
            sets = ", ".join(f"{k}=?" for k in allowed)
            db.execute(f"UPDATE watches SET {sets} WHERE id=?", (*allowed.values(), wid))
        self._wake.set()
        return self.get(w["id"])

    def remove(self, wid: str) -> None:
        db.execute("DELETE FROM watches WHERE id=?", (wid,))

    async def check(self, wid: str) -> dict:
        """Look for new files now and queue them."""
        if wid in self._checking:
            return {"id": wid, "queued": 0, "note": "busy"}
        self._checking.add(wid)
        w = self.get(wid)
        from .tasks import get_tasks
        try:
            f = dict(w["filters"])
            if "types" in f:
                f["types_"] = f.pop("types")
            res = await get_tasks().enqueue_downloads(
                w["account"], f"watch:{w['chat_title']}", chat=str(w["chat_id"]), limit=500, oldest_first=True,
                subdir=w["subdir"], skip_approval=True, min_id=int(w["last_message_id"] or 0), **f)
            acc, client = await accounts.client(w["account"])
            entity = await readers._entity(client, w["chat_id"])
            latest = w["last_message_id"]
            async for m in client.iter_messages(entity, limit=1):
                latest = max(latest, m.id)
            db.execute("UPDATE watches SET last_message_id=?, last_check=?, last_error='', downloaded=downloaded+? WHERE id=?",
                       (latest, time.time(), res["queued"], wid))
            if res["queued"]:
                bus.log("info", f"watch:{w['chat_title']}", L("订阅发现新文件", "Watch found new files"),
                        f"{res['queued']} · {res['total_size_human']}", watch_id=wid)
            return {"id": wid, "queued": res["queued"], "total_size_human": res["total_size_human"]}
        except Exception as e:
            db.execute("UPDATE watches SET last_check=?, last_error=? WHERE id=?",
                       (time.time(), f"{type(e).__name__}: {e}", wid))
            raise
        finally:
            self._checking.discard(wid)

    async def run_forever(self) -> None:
        while True:
            now = time.time()
            for w in self.list():
                if not w["enabled"]:
                    continue
                acc = accounts.accounts.get(w["account"])
                if not acc or acc.status != "ready":
                    continue
                if now - (w["last_check"] or 0) >= w["interval_min"] * 60:
                    try:
                        await self.check(w["id"])
                    except Exception as e:
                        bus.log("error", f"watch:{w['chat_title']}", L("订阅检查失败", "Watch check failed"), str(e))
            self._wake.clear()
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=60)
            except asyncio.TimeoutError:
                pass


watches = WatchManager()
