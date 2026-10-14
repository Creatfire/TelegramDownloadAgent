"""Agent support: questions to the user, chat notes (shared memory), per-agent quotas and usage,
the Telegram request budget, and metrics for the dashboard."""
from __future__ import annotations

import asyncio
import time
import uuid
from collections import deque

from .activity import bus
from .config import settings
from .db import db, dumps, loads
from .i18n import L

db.conn.executescript("""
CREATE TABLE IF NOT EXISTS questions (
    id TEXT PRIMARY KEY, workflow_id TEXT, step_id TEXT, agent TEXT, question TEXT, options TEXT,
    allow_text INTEGER, answer TEXT, status TEXT, created REAL, answered REAL
);
CREATE TABLE IF NOT EXISTS notes (
    account TEXT, chat_id INTEGER, chat_title TEXT, text TEXT, author TEXT, updated REAL, PRIMARY KEY (account, chat_id)
);
CREATE TABLE IF NOT EXISTS usage (
    day TEXT, agent TEXT, requests INTEGER DEFAULT 0, bytes INTEGER DEFAULT 0, PRIMARY KEY (day, agent)
);
CREATE TABLE IF NOT EXISTS metrics (
    ts INTEGER PRIMARY KEY, speed REAL, running INTEGER, tg_requests INTEGER, floods INTEGER
);
""")


def today() -> str:
    return time.strftime("%Y-%m-%d")


# ---------------------------------------------------------------- questions
class Questions:
    def __init__(self) -> None:
        self._events: dict[str, asyncio.Event] = {}
        db.execute("UPDATE questions SET status='expired' WHERE status='open'")

    def pending(self) -> list[dict]:
        return [self._public(r) for r in db.all("SELECT * FROM questions WHERE status='open' ORDER BY created")]

    def get(self, qid: str) -> dict | None:
        r = db.one("SELECT * FROM questions WHERE id=?", (qid,))
        return self._public(r) if r else None

    @staticmethod
    def _public(r: dict) -> dict:
        return {**r, "options": loads(r["options"], []), "allow_text": bool(r["allow_text"])}

    async def ask(self, agent: str, question: str, options: list[str] | None, allow_text: bool,
                  timeout: float, workflow_id: str = "", step_id: str = "") -> dict:
        qid = uuid.uuid4().hex[:10]
        row = {"id": qid, "workflow_id": workflow_id, "step_id": step_id, "agent": agent, "question": question[:1000],
               "options": dumps([str(o)[:200] for o in (options or [])][:12]), "allow_text": int(allow_text or not options),
               "answer": None, "status": "open", "created": time.time(), "answered": None}
        db.upsert("questions", row)
        ev = self._events[qid] = asyncio.Event()
        q = self._public(row)
        bus.emit("question", q)
        bus.log("warn", agent, L("AI 在等你回答", "The AI is waiting for your answer"), question[:200], question_id=qid)
        try:
            await asyncio.wait_for(ev.wait(), timeout=max(10, min(float(timeout or 600), 3600)))
        except asyncio.TimeoutError:
            db.execute("UPDATE questions SET status='expired' WHERE id=? AND status='open'", (qid,))
        finally:
            self._events.pop(qid, None)
        q = self.get(qid)
        bus.emit("question", q)
        if q["status"] == "answered":
            return {"answered": True, "answer": q["answer"]}
        return {"answered": False, "status": q["status"],
                "hint": "The user did not answer in time. Decide conservatively or ask again later."}

    def answer(self, qid: str, answer: str) -> dict:
        db.execute("UPDATE questions SET answer=?, status='answered', answered=? WHERE id=? AND status='open'",
                   (str(answer)[:2000], time.time(), qid))
        ev = self._events.get(qid)
        if ev:
            ev.set()
        q = self.get(qid)
        bus.emit("question", q)
        return q

    def dismiss(self, qid: str) -> None:
        db.execute("UPDATE questions SET status='dismissed' WHERE id=? AND status='open'", (qid,))
        ev = self._events.get(qid)
        if ev:
            ev.set()


questions = Questions()


# ---------------------------------------------------------------- notes
def get_note(account: str, chat_id: int) -> dict | None:
    return db.one("SELECT * FROM notes WHERE account=? AND chat_id=?", (account, chat_id))


def set_note(account: str, chat_id: int, chat_title: str, text: str, author: str, append: bool = False) -> dict:
    prev = get_note(account, chat_id)
    if append and prev and prev["text"]:
        text = prev["text"].rstrip() + "\n" + text
    db.upsert("notes", {"account": account, "chat_id": chat_id, "chat_title": chat_title, "text": text[:8000],
                        "author": author, "updated": time.time()})
    return get_note(account, chat_id)


def all_notes(account: str | None = None) -> list[dict]:
    if account:
        return db.all("SELECT * FROM notes WHERE account=? ORDER BY updated DESC", (account,))
    return db.all("SELECT * FROM notes ORDER BY updated DESC")


def delete_note(account: str, chat_id: int) -> None:
    db.execute("DELETE FROM notes WHERE account=? AND chat_id=?", (account, chat_id))


# ---------------------------------------------------------------- quotas and usage
def limits_for(agent: str) -> dict:
    per = (settings.get("agent_limits") or {}).get(agent, {})
    return {
        "daily_requests": int(per.get("daily_requests", settings.get("default_daily_requests") or 0) or 0),
        "daily_gb": float(per.get("daily_gb", settings.get("default_daily_gb") or 0) or 0),
        "chats": [str(c).lower().lstrip("@") for c in per.get("chats", []) if str(c).strip()],
        "blocked": bool(per.get("blocked")),
    }


def usage_for(agent: str, day: str | None = None) -> dict:
    r = db.one("SELECT * FROM usage WHERE day=? AND agent=?", (day or today(), agent))
    return {"requests": r["requests"] if r else 0, "bytes": r["bytes"] if r else 0}


def count_request(agent: str) -> None:
    db.execute("INSERT INTO usage(day, agent, requests, bytes) VALUES (?,?,1,0) "
               "ON CONFLICT(day, agent) DO UPDATE SET requests = requests + 1", (today(), agent))


def count_bytes(agent: str, n: int) -> None:
    db.execute("INSERT INTO usage(day, agent, requests, bytes) VALUES (?,?,0,?) "
               "ON CONFLICT(day, agent) DO UPDATE SET bytes = bytes + ?", (today(), agent, n, n))


class QuotaError(Exception):
    pass


def check_request(agent: str, chats: list) -> None:
    """Raise QuotaError when the agent is blocked, over its daily request quota, or touching a chat it may not use."""
    if agent in ("console",) or agent.startswith(("watch:", "schedule", "replay")):
        return
    lim = limits_for(agent)
    if lim["blocked"]:
        raise QuotaError(L(f"用户已在控制台停用 {agent}", f"The user has disabled {agent} in the console"))
    if lim["daily_requests"] and usage_for(agent)["requests"] >= lim["daily_requests"]:
        raise QuotaError(L(f"{agent} 今日请求次数已达上限（{lim['daily_requests']}）。请让用户在控制台提高额度。",
                           f"{agent} reached its daily request quota ({lim['daily_requests']}). Ask the user to raise it in the console."))
    if lim["chats"]:
        for c in chats:
            if c and str(c).lower().lstrip("@") not in lim["chats"]:
                raise QuotaError(L(f"{agent} 只被允许访问：{', '.join(lim['chats'])}", f"{agent} may only access: {', '.join(lim['chats'])}"))


def over_byte_quota(agent: str, extra: int) -> bool:
    lim = limits_for(agent)
    if not lim["daily_gb"]:
        return False
    return usage_for(agent)["bytes"] + extra > lim["daily_gb"] * 1024 ** 3


def agents_overview() -> list[dict]:
    names = {r["agent"] for r in db.all("SELECT DISTINCT agent FROM sessions")} | set(settings.get("agent_limits") or {})
    out = []
    for a in sorted(n for n in names if n and n not in ("console",) and not n.startswith(("replay", "schedule"))):
        out.append({"agent": a, "limits": limits_for(a), "today": usage_for(a)})
    return out


# ---------------------------------------------------------------- Telegram request budget
class RequestBudget:
    """Counts every Telegram API call (downloads' file parts excluded) and spaces them out to a per-minute budget."""

    def __init__(self) -> None:
        self.calls: deque[float] = deque()
        self.minute_count = 0
        self.floods = 0
        self.today_count = 0
        self.today = today()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        per_min = int(settings.get("tg_requests_per_minute") or 0)
        async with self._lock:
            now = time.time()
            while self.calls and now - self.calls[0] > 60:
                self.calls.popleft()
            if per_min and len(self.calls) >= per_min:
                await asyncio.sleep(60 - (now - self.calls[0]) + 0.05)
            self.calls.append(time.time())
        if self.today != today():
            self.today, self.today_count = today(), 0
        self.today_count += 1
        self.minute_count += 1

    def flood(self) -> None:
        self.floods += 1

    def snapshot(self) -> dict:
        now = time.time()
        return {"last_minute": sum(1 for t in self.calls if now - t <= 60), "today": self.today_count,
                "per_minute_limit": int(settings.get("tg_requests_per_minute") or 0), "floods_since_start": self.floods}


budget = RequestBudget()


# ---------------------------------------------------------------- metrics (one row per minute)
async def metrics_loop(get_speed) -> None:
    last_floods = 0
    while True:
        await asyncio.sleep(60 - time.time() % 60)
        speed, running = get_speed()
        req, budget.minute_count = budget.minute_count, 0
        floods, last_floods = budget.floods - last_floods, budget.floods
        db.execute("INSERT OR REPLACE INTO metrics(ts, speed, running, tg_requests, floods) VALUES (?,?,?,?,?)",
                   (int(time.time() // 60 * 60), speed, running, req, floods))
        db.execute("DELETE FROM metrics WHERE ts < ?", (int(time.time()) - 30 * 86400,))
