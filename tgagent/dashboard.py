"""Aggregates for the console dashboard (all from local data; nothing here contacts Telegram)."""
from __future__ import annotations

import time

from . import assist
from .db import db


def _day(ts: float) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(ts))


def build(tm, days: int = 7) -> dict:
    now = time.time()
    since = now - days * 86400
    today = time.strftime("%Y-%m-%d")

    # throughput: metrics are one row per minute; average them into ~120 points
    rows = db.all("SELECT ts, speed, running, tg_requests, floods FROM metrics WHERE ts >= ? ORDER BY ts", (int(now - 86400),))
    bucket = 600
    speed, reqs = {}, {}
    for r in rows:
        b = r["ts"] // bucket * bucket
        speed.setdefault(b, []).append(r["speed"] or 0)
        reqs.setdefault(b // 6 * 6, [0, 0])
        hb = r["ts"] // 3600 * 3600
        reqs.setdefault(hb, [0, 0])
        reqs[hb][0] += r["tg_requests"] or 0
        reqs[hb][1] += r["floods"] or 0
    speed_series = [{"t": b, "v": sum(v) / len(v)} for b, v in sorted(speed.items())]
    req_series = [{"t": b, "requests": v[0], "floods": v[1]} for b, v in sorted(reqs.items()) if b % 3600 == 0]

    # downloads per day
    per_day = {(_day(now - i * 86400)): {"bytes": 0, "files": 0} for i in range(days - 1, -1, -1)}
    for r in db.all("SELECT finished, size FROM downloads WHERE finished >= ?", (since,)):
        d = _day(r["finished"])
        if d in per_day:
            per_day[d]["bytes"] += r["size"] or 0
            per_day[d]["files"] += 1
    daily = [{"day": d, **v} for d, v in per_day.items()]

    by_chat = db.all("SELECT COALESCE(chat_title, chat_id) AS chat, SUM(size) AS bytes, COUNT(*) AS files FROM downloads "
                     "WHERE finished >= ? GROUP BY chat_id ORDER BY bytes DESC LIMIT 8", (since,))
    library = db.all("SELECT kind, COUNT(*) AS files, COALESCE(SUM(size),0) AS bytes FROM files GROUP BY kind ORDER BY bytes DESC")

    agents = db.all("SELECT w.agent AS agent, COUNT(*) AS calls, SUM(CASE WHEN s.status='error' THEN 1 ELSE 0 END) AS errors "
                    "FROM steps s JOIN workflows w ON w.id = s.workflow_id WHERE s.ts >= ? GROUP BY w.agent ORDER BY calls DESC LIMIT 8",
                    (since,))
    tools = db.all("SELECT tool, COUNT(*) AS calls, AVG(ms) AS avg_ms FROM steps WHERE ts >= ? GROUP BY tool ORDER BY calls DESC LIMIT 10",
                   (since,))
    scatter = db.all("SELECT s.ts AS t, s.ms AS ms, s.tool AS tool, s.status AS status FROM steps s WHERE s.ts >= ? AND s.ms IS NOT NULL "
                     "ORDER BY s.ts DESC LIMIT 600", (since,))
    wf_status = db.all("SELECT status, COUNT(*) AS n FROM workflows WHERE created >= ? GROUP BY status", (since,))

    task_status: dict[str, int] = {}
    for t in tm.tasks.values():
        if t.kind == "download":
            task_status[t.status] = task_status.get(t.status, 0) + 1

    dl_today = db.one("SELECT COALESCE(SUM(size),0) AS b, COUNT(*) AS n FROM downloads WHERE finished >= ?",
                      (time.mktime(time.strptime(today, "%Y-%m-%d")),))
    avg_speed = db.one("SELECT AVG(speed) AS v FROM metrics WHERE ts >= ? AND running > 0", (int(since),))
    lib = db.one("SELECT COUNT(*) AS n, COALESCE(SUM(size),0) AS b FROM files")
    archived = db.one("SELECT COUNT(*) AS n FROM messages")
    floods_today = db.one("SELECT COALESCE(SUM(floods),0) AS n FROM metrics WHERE ts >= ?",
                          (int(time.mktime(time.strptime(today, "%Y-%m-%d"))),))
    return {
        "days": days,
        "kpi": {
            "downloaded_today": dl_today["b"], "files_today": dl_today["n"],
            "avg_speed": avg_speed["v"] or 0, "tg_requests_today": assist.budget.snapshot()["today"],
            "floods_today": floods_today["n"], "library_files": lib["n"], "library_bytes": lib["b"],
            "archived_messages": archived["n"],
            "active_workflows": (db.one("SELECT COUNT(*) AS n FROM workflows WHERE status='active'") or {}).get("n", 0),
        },
        "speed_24h": speed_series, "requests_24h": req_series, "daily": daily, "by_chat": by_chat,
        "library": library, "agents": agents, "tools": tools, "scatter": scatter,
        "workflow_status": wf_status, "task_status": [{"status": k, "n": v} for k, v in task_status.items()],
    }
