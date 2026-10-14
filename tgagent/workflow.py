"""Workflow tracking.

Session  = one AI client connection (an MCP session / one stdio bridge process / the console).
Workflow = one user request inside a session. Agents open it explicitly with tg_start_workflow and
           close it with tg_finish_workflow. Calls made without one go to an implicit workflow so
           nothing is lost.
Step     = one tool call. Parents are inferred from data flow: if a step's arguments use a chat,
           message or task that an earlier step produced, it is linked to that step; otherwise it
           follows the previous step.
"""
from __future__ import annotations

import contextvars
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from . import readers
from .activity import bus
from .config import settings
from .db import db, dumps, loads
from .i18n import L

try:
    db.execute("ALTER TABLE steps ADD COLUMN lanes TEXT")
except Exception:
    pass

GENERAL = {"key": "general", "title": ""}
_CHAT_ARGS = ("intro_chat", "chat", "chat_a", "files_chat", "chat_b")


_lane_alias: dict[str, dict] = {}   # "c:username" -> canonical lane learnt from results


def lane_for(value) -> dict:
    """Canonical lane (one per chat) for a chat argument: usernames and links map to the numeric id when known."""
    cr = readers.parse_ref(value)
    if cr.chat is None:
        return dict(GENERAL)
    known = _lane_alias.get(f"c:{str(cr.chat).lower()}")
    if known:
        return dict(known)
    if isinstance(cr.chat, int):
        row = db.one("SELECT chat_id, title FROM chats WHERE chat_id=?", (cr.chat,))
        return {"key": f"c:{cr.chat}", "title": (row or {}).get("title") or str(cr.chat)}
    row = db.one("SELECT chat_id, title FROM chats WHERE lower(username)=?", (str(cr.chat).lower(),))
    if row:
        return {"key": f"c:{row['chat_id']}", "title": row["title"]}
    return {"key": f"c:{str(cr.chat).lower()}", "title": "@" + str(cr.chat)}


def lanes_from_args(args: dict) -> list[dict]:
    out = []
    for k in _CHAT_ARGS:
        if args.get(k):
            out.append(lane_for(args[k]))
    for c in (args.get("chats") or [])[:2]:
        out.append(lane_for(c))
    for link in (args.get("links") or [])[:1] + ([args["link"]] if args.get("link") else []):
        out.append(lane_for(link))
    seen, uniq = set(), []
    for ln in out:
        if ln["key"] not in seen:
            seen.add(ln["key"])
            uniq.append(ln)
    return uniq[:2]


# The step currently executing (used by tasks.py to attach downloads to it)
current_step: contextvars.ContextVar["Step | None"] = contextvars.ContextVar("current_step", default=None)

POLL_TOOLS = {"tg_tasks", "tg_wait_tasks", "tg_list_accounts", "tg_index_status"}

# Set by the MCP layer when the client asked for progress notifications: async (progress, total, message)
progress_reporter: contextvars.ContextVar = contextvars.ContextVar("progress_reporter", default=None)
MAX_RESULT_CHARS = 20000


@dataclass
class Step:
    id: str
    workflow_id: str
    seq: int
    tool: str
    args: dict
    status: str = "running"
    summary: str = ""
    result: str = ""
    error: str = ""
    parents: list[dict] = field(default_factory=list)   # [{"id": step_id, "kind": "data"|"seq"}]
    produced: set[str] = field(default_factory=set)
    task_ids: list[str] = field(default_factory=list)
    polls: int = 0
    ts: float = field(default_factory=time.time)
    ms: int | None = None
    lanes: list[dict] = field(default_factory=list)

    def public(self, with_result: bool = False) -> dict:
        d = {"id": self.id, "workflow_id": self.workflow_id, "seq": self.seq, "tool": self.tool, "args": self.args,
             "status": self.status, "summary": self.summary, "error": self.error, "parents": self.parents,
             "task_ids": self.task_ids, "polls": self.polls, "ts": self.ts, "ms": self.ms, "lanes": self.lanes}
        if with_result:
            d["result"] = self.result
        return d

    def save(self) -> None:
        db.upsert("steps", {
            "id": self.id, "workflow_id": self.workflow_id, "seq": self.seq, "tool": self.tool,
            "args": dumps(self.args), "status": self.status, "summary": self.summary, "result": self.result,
            "error": self.error, "parents": dumps(self.parents), "produced": dumps(sorted(self.produced)[:5000]),
            "task_ids": dumps(self.task_ids), "polls": self.polls, "ts": self.ts, "ms": self.ms,
            "lanes": dumps(self.lanes)})


@dataclass
class Workflow:
    id: str
    session_id: str
    agent: str
    title: str
    goal: str = ""
    explicit: bool = True
    status: str = "active"     # active / done / failed / canceled / idle
    summary: str = ""
    created: float = field(default_factory=time.time)
    updated: float = field(default_factory=time.time)
    ended: float | None = None
    steps: list[Step] = field(default_factory=list)
    polls: int = 0

    def public(self) -> dict:
        return {"id": self.id, "session_id": self.session_id, "agent": self.agent, "title": self.title,
                "goal": self.goal, "explicit": self.explicit, "status": self.status, "summary": self.summary,
                "created": self.created, "updated": self.updated, "ended": self.ended,
                "steps": len(self.steps), "polls": self.polls}

    def save(self) -> None:
        db.upsert("workflows", {
            "id": self.id, "session_id": self.session_id, "agent": self.agent, "title": self.title,
            "goal": self.goal, "explicit": int(self.explicit), "status": self.status, "summary": self.summary,
            "created": self.created, "updated": self.updated, "ended": self.ended,
            "steps": len(self.steps), "polls": self.polls})


# ---------------------------------------------------------------- reference extraction

def _chat_refs(chat: Any) -> set[str]:
    if chat in (None, ""):
        return set()
    cr = readers.parse_ref(chat)
    out = set()
    if cr.chat is not None:
        out.add(f"c:{str(cr.chat).lower()}")
    if cr.msg_id:
        out.add(f"m:{cr.msg_id}")
    return out


def produced_refs(result: Any) -> set[str]:
    """Values a step hands to later steps: chats, message ids, task ids."""
    refs: set[str] = set()
    if not isinstance(result, dict):
        return refs

    def chat(c):
        if isinstance(c, dict):
            if c.get("id") is not None:
                refs.add(f"c:{c['id']}")
            if c.get("username"):
                refs.add(f"c:{c['username'].lower()}")

    chat(result.get("chat"))
    if "title" in result and "type" in result:     # tg_resolve_chat
        chat(result)
    def items(key):
        v = result.get(key)
        return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []

    for d in items("dialogs"):
        chat(d)
    for m in items("messages"):
        refs.add(f"m:{m.get('id')}")
        chat(m.get("chat"))
    for f in items("files") + items("sample"):
        refs.add(f"m:{f.get('message_id')}")
        if f.get("chat_id") is not None:
            refs.add(f"c:{f['chat_id']}")
    if result.get("id") is not None and "date" in result:   # tg_get_message
        refs.add(f"m:{result['id']}")
    for a in items("album_items"):
        refs.add(f"m:{a.get('id')}")
    for t in items("tasks"):
        tid = t.get("task_id") or t.get("id")
        if tid:
            refs.add(f"t:{tid}")
    if result.get("task_id"):
        refs.add(f"t:{result['task_id']}")
    return refs


def used_refs(args: dict) -> set[str]:
    refs = set()
    refs |= _chat_refs(args.get("chat"))
    for c in args.get("chats", []) or []:
        refs |= _chat_refs(c)
    for k in ("chat_a", "chat_b", "intro_chat", "files_chat"):
        refs |= _chat_refs(args.get(k))
    for link in args.get("links", []) or []:
        refs |= _chat_refs(link)
    refs |= _chat_refs(args.get("link"))
    for mid in args.get("message_ids", []) or []:
        refs.add(f"m:{mid}")
    if args.get("message_id"):
        refs.add(f"m:{args['message_id']}")
    if args.get("offset_id"):
        refs.add(f"m:{args['offset_id']}")
    for tid in args.get("task_ids", []) or []:
        refs.add(f"t:{tid}")
    return refs


# ---------------------------------------------------------------- manager

class WorkflowManager:
    def __init__(self) -> None:
        self.active: dict[str, Workflow] = {}       # session_id -> active workflow
        self.loaded: dict[str, Workflow] = {}       # workflow_id -> workflow (in memory)

    # sessions
    def touch_session(self, session_id: str, agent: str, transport: str) -> None:
        now = time.time()
        row = db.one("SELECT id FROM sessions WHERE id=?", (session_id,))
        if row:
            db.execute("UPDATE sessions SET last_active=?, agent=? WHERE id=?", (now, agent, session_id))
        else:
            db.upsert("sessions", {"id": session_id, "agent": agent, "transport": transport,
                                   "created": now, "last_active": now})

    # workflows
    def _emit(self, wf: Workflow) -> None:
        bus.emit("workflow", wf.public())

    def start(self, session_id: str, agent: str, title: str, goal: str = "", explicit: bool = True) -> Workflow:
        prev = self.active.get(session_id)
        if prev and prev.status == "active":
            self.finish(session_id, status="done" if prev.explicit else "idle")
        wf = Workflow(id=uuid.uuid4().hex[:12], session_id=session_id, agent=agent,
                      title=(title or "").strip()[:120] or L("未命名工作流", "Untitled workflow"),
                      goal=(goal or "").strip()[:500], explicit=explicit)
        self.active[session_id] = wf
        self.loaded[wf.id] = wf
        wf.save()
        self._emit(wf)
        if explicit:
            bus.log("info", agent, L("开始工作流", "Workflow started"), wf.title, workflow_id=wf.id)
        return wf

    def finish(self, session_id: str, summary: str = "", status: str = "done") -> Workflow | None:
        wf = self.active.pop(session_id, None)
        if not wf:
            return None
        wf.status = status if status in ("done", "failed", "canceled", "idle") else "done"
        wf.summary = (summary or "").strip()[:2000]
        wf.ended = wf.updated = time.time()
        wf.save()
        self._emit(wf)
        if wf.explicit:
            bus.log("success" if wf.status == "done" else "warn", wf.agent,
                    L("结束工作流", "Workflow finished"), f"{wf.title} · {wf.summary}"[:300], workflow_id=wf.id)
        return wf

    def current(self, session_id: str, agent: str) -> tuple[Workflow, bool]:
        """Active workflow of the session; creates an implicit one if needed. Returns (wf, created_implicit)."""
        wf = self.active.get(session_id)
        idle = float(settings.get("workflow_idle_seconds") or 1800)
        if wf and not wf.explicit and time.time() - wf.updated > idle:
            self.finish(session_id, status="idle")
            wf = None
        if wf:
            return wf, False
        return self.start(session_id, agent, L("未命名工作流", "Untitled workflow"), explicit=False), True

    # steps
    def begin_step(self, wf: Workflow, tool: str, args: dict) -> tuple[Step, bool]:
        """Create (or reuse, for polling tools) a step. Returns (step, is_poll)."""
        wf.updated = time.time()
        if tool in POLL_TOOLS:
            # Polling calls never become nodes: count them on the step whose tasks they ask about,
            # otherwise on the latest identical call, otherwise on the workflow itself.
            tids = {f"t:{t}" for t in args.get("task_ids", []) or []}
            target = None
            if tids:
                target = next((s for s in reversed(wf.steps) if tids & s.produced), None)
            if not target:
                target = next((s for s in reversed(wf.steps) if s.tool == tool and s.args == args), None)
            if target:
                target.polls += 1
                target.save()
                bus.emit("step", target.public())
                return target, True
            if wf.steps and tool == "tg_tasks":
                wf.polls += 1
                wf.save()
                self._emit(wf)
                return Step(id="", workflow_id=wf.id, seq=-1, tool=tool, args=args), True

        uses = used_refs(args)
        parents: list[dict] = []
        if uses:
            covered: set[str] = set()
            for s in reversed(wf.steps):
                hit = (uses & s.produced) - covered
                if hit:
                    parents.append({"id": s.id, "kind": "data"})
                    covered |= hit
                if covered >= uses:
                    break
        if not parents and wf.steps:
            parents.append({"id": wf.steps[-1].id, "kind": "seq"})
        lanes = lanes_from_args(args)
        if not lanes:   # e.g. waiting on tasks: belongs to the lane of the step that produced them
            src = next((st for st in wf.steps for pp in parents if pp["kind"] == "data" and st.id == pp["id"]), None)
            lanes = list(src.lanes[:1]) if src and src.lanes else [dict(GENERAL)]
        step = Step(id=uuid.uuid4().hex[:12], workflow_id=wf.id, seq=len(wf.steps) + 1, tool=tool,
                    args=args, parents=parents, lanes=lanes)
        wf.steps.append(step)
        step.save()
        wf.save()
        bus.emit("step", step.public())
        self._emit(wf)
        return step, False

    def end_step(self, wf: Workflow, step: Step, ok: bool, result: Any, summary: str, ms: int) -> None:
        if not step.id:
            return
        step.ms = ms
        if ok:
            step.status = "done"
            step.summary = summary
            step.produced |= produced_refs(result)
            chat = result.get("chat") if isinstance(result, dict) else None
            if isinstance(result, dict) and "title" in result and "type" in result and result.get("id") is not None:
                chat = result
            if isinstance(chat, dict) and chat.get("id") is not None and step.lanes and step.lanes[0]["key"] != "general":
                old_key = step.lanes[0]["key"]
                step.lanes[0] = {"key": f"c:{chat['id']}", "title": chat.get("title") or step.lanes[0]["title"]}
                if old_key != step.lanes[0]["key"]:   # the argument (e.g. a username) now maps to this chat
                    _lane_alias[old_key] = dict(step.lanes[0])
                    for other in (wf.steps if wf else []):
                        other.lanes = [dict(step.lanes[0]) if ln["key"] == old_key else ln for ln in other.lanes]
                if chat.get("username"):
                    _lane_alias[f"c:{chat['username'].lower()}"] = dict(step.lanes[0])
                _lane_alias[f"c:{chat['id']}"] = dict(step.lanes[0])
                for other in (wf.steps if wf else []):   # earlier steps that named the chat by username
                    for i, ln in enumerate(other.lanes):
                        if ln["key"] in {f"c:{str(chat.get('username') or '').lower()}"} and chat.get("username"):
                            other.lanes[i] = dict(step.lanes[0])
            text = dumps(result)
            step.result = text if len(text) <= MAX_RESULT_CHARS else text[:MAX_RESULT_CHARS] + "…"
        else:
            step.status = "error"
            step.error = str(result)
        wf.updated = time.time()
        step.save()
        wf.save()
        bus.emit("step", step.public())
        self._emit(wf)

    def attach_tasks(self, step: Step | None, task_ids: list[str]) -> None:
        if not step or not step.id or not task_ids:
            return
        step.task_ids.extend(task_ids)
        step.produced |= {f"t:{t}" for t in task_ids}
        step.save()
        bus.emit("step", step.public())

    # queries for the UI
    def list(self, limit: int = 100) -> list[dict]:
        rows = db.all("SELECT * FROM workflows ORDER BY updated DESC LIMIT ?", (limit,))
        for r in rows:
            r["explicit"] = bool(r["explicit"])
            wf = self.loaded.get(r["id"])
            if wf:
                r.update(wf.public())
        return rows

    def detail(self, wf_id: str) -> dict | None:
        wf = self.loaded.get(wf_id)
        if wf:
            head = wf.public()
            steps = [s.public(with_result=False) for s in wf.steps]
        else:
            head = db.one("SELECT * FROM workflows WHERE id=?", (wf_id,))
            if not head:
                return None
            head["explicit"] = bool(head["explicit"])
            steps = []
            for r in db.all("SELECT * FROM steps WHERE workflow_id=? ORDER BY seq", (wf_id,)):
                steps.append({**{k: r[k] for k in ("id", "workflow_id", "seq", "tool", "status", "summary",
                                                   "error", "polls", "ts", "ms")},
                              "args": loads(r["args"], {}), "parents": loads(r["parents"], []),
                              "task_ids": loads(r["task_ids"], []), "lanes": loads(r.get("lanes"), [])})
        return {"workflow": head, "steps": steps}

    def step_result(self, step_id: str) -> dict | None:
        for wf in self.loaded.values():
            for s in wf.steps:
                if s.id == step_id:
                    return s.public(with_result=True)
        r = db.one("SELECT * FROM steps WHERE id=?", (step_id,))
        if not r:
            return None
        return {"id": r["id"], "tool": r["tool"], "args": loads(r["args"], {}), "result": r["result"],
                "error": r["error"], "status": r["status"]}

    def rename(self, wf_id: str, title: str) -> None:
        wf = self.loaded.get(wf_id)
        if wf:
            wf.title = title[:120]
            wf.save()
            self._emit(wf)
        else:
            db.execute("UPDATE workflows SET title=? WHERE id=?", (title[:120], wf_id))

    def delete(self, wf_id: str) -> None:
        wf = self.loaded.pop(wf_id, None)
        if wf and self.active.get(wf.session_id) is wf:
            self.active.pop(wf.session_id, None)
        db.execute("DELETE FROM steps WHERE workflow_id=?", (wf_id,))
        db.execute("DELETE FROM workflows WHERE id=?", (wf_id,))

    def close_stale_on_startup(self) -> None:
        db.execute("UPDATE workflows SET status='idle', ended=updated WHERE status='active'")


workflows = WorkflowManager()
