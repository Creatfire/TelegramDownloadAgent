"""Recipes: reusable, parameterised workflows.

A recipe is a list of tool calls. Argument strings may contain "{param}" placeholders and references to
earlier results such as "{{2.task_id}}" or "{{3.tasks[*].task_id}}" (step numbers start at 1).
Recipes can be run from the console, by an agent (tg_run_recipe), on a schedule, and are offered to MCP
clients as prompts (slash commands in Claude Code)."""
from __future__ import annotations

import asyncio
import copy
import re
import time
import uuid
from typing import Any

from .activity import bus
from .db import db, dumps, loads
from .i18n import L

db.conn.executescript("""
CREATE TABLE IF NOT EXISTS recipes (
    id TEXT PRIMARY KEY, name TEXT, title TEXT, description TEXT, steps TEXT, params TEXT,
    schedule TEXT, schedule_params TEXT, builtin INTEGER, created REAL, last_run REAL, runs INTEGER DEFAULT 0
);
""")

SKIP = {"tg_start_workflow", "tg_finish_workflow", "tg_tasks", "tg_list_accounts", "tg_index_status", "tg_task_control"}

BUILTIN = [
    {"id": "channel-inventory", "name": "channel_inventory", "title": "整理频道清单 / Channel inventory",
     "description": "Index every file of a chat into the local library and report counts and total size.",
     "params": [{"name": "chat", "description": "Channel (@username, link or id)", "required": True}],
     "steps": [{"tool": "tg_resolve_chat", "args": {"chat": "{chat}"}},
               {"tool": "tg_index_chat", "args": {"chat": "{chat}"}},
               {"tool": "tg_wait_tasks", "args": {"task_ids": ["{{2.task_id}}"], "timeout_s": 1800}},
               {"tool": "tg_search_files", "args": {"chats": ["{chat}"], "sort": "size", "limit": 20}}]},
    {"id": "download-latest", "name": "download_latest", "title": "下载最新文件 / Download latest files",
     "description": "Plan and download the newest files of a chat (split archives are completed automatically).",
     "params": [{"name": "chat", "description": "Channel", "required": True},
                {"name": "count", "description": "How many files (default 5)", "required": False, "default": "5"},
                {"name": "types", "description": "Kinds, comma separated (document,video,audio,photo)", "required": False, "default": ""}],
     "steps": [{"tool": "tg_plan_download", "args": {"chat": "{chat}", "limit": "{count}", "types": "{types}"}},
               {"tool": "tg_download", "args": {"chat": "{chat}", "limit": "{count}", "types": "{types}"}},
               {"tool": "tg_wait_tasks", "args": {"task_ids": "{{2.tasks[*].task_id}}", "timeout_s": 1800}}]},
    {"id": "compare-chats", "name": "compare_chats", "title": "对比两个频道 / Compare two chats",
     "description": "Index two chats and list what they share and what only one of them has.",
     "params": [{"name": "chat_a", "description": "First channel", "required": True},
                {"name": "chat_b", "description": "Second channel", "required": True}],
     "steps": [{"tool": "tg_index_chat", "args": {"chat": "{chat_a}"}},
               {"tool": "tg_index_chat", "args": {"chat": "{chat_b}"}},
               {"tool": "tg_wait_tasks", "args": {"task_ids": ["{{1.task_id}}", "{{2.task_id}}"], "timeout_s": 1800}},
               {"tool": "tg_compare_chats", "args": {"chat_a": "{chat_a}", "chat_b": "{chat_b}", "by": "stem"}}]},
    {"id": "match-intro", "name": "match_intro_to_files", "title": "介绍帖对应下载 / Match intro posts to files",
     "description": "Read an intro channel, index the download channel, and pair each intro post with its files.",
     "params": [{"name": "intro_chat", "description": "Channel with the descriptions", "required": True},
                {"name": "files_chat", "description": "Channel with the files", "required": True},
                {"name": "posts", "description": "How many intro posts (default 30)", "required": False, "default": "30"}],
     "steps": [{"tool": "tg_get_messages", "args": {"chat": "{intro_chat}", "limit": "{posts}", "text_max": 200}},
               {"tool": "tg_index_chat", "args": {"chat": "{files_chat}"}},
               {"tool": "tg_wait_tasks", "args": {"task_ids": ["{{2.task_id}}"], "timeout_s": 1800}},
               {"tool": "tg_match_posts", "args": {"intro_chat": "{intro_chat}", "files_chat": "{files_chat}", "posts": "{posts}"}}]},
]

_PARAM = re.compile(r"\{([a-zA-Z_][\w]*)\}")
_REF = re.compile(r"\{\{(\d+)\.([^}]+)\}\}")


def _ensure_builtins() -> None:
    for r in BUILTIN:
        if not db.one("SELECT 1 FROM recipes WHERE id=?", (r["id"],)):
            db.upsert("recipes", {"id": r["id"], "name": r["name"], "title": r["title"], "description": r["description"],
                                  "steps": dumps(r["steps"]), "params": dumps(r["params"]), "schedule": None,
                                  "schedule_params": None, "builtin": 1, "created": time.time(), "last_run": None, "runs": 0})


_ensure_builtins()


def _public(r: dict) -> dict:
    return {**r, "steps": loads(r["steps"], []), "params": loads(r["params"], []), "schedule": loads(r["schedule"], None),
            "schedule_params": loads(r["schedule_params"], {}), "builtin": bool(r["builtin"])}


def list_recipes() -> list[dict]:
    return [_public(r) for r in db.all("SELECT * FROM recipes ORDER BY builtin DESC, created")]


def get(key: str) -> dict:
    r = db.one("SELECT * FROM recipes WHERE id=? OR name=?", (key, key))
    if not r:
        raise ValueError(L(f"配方不存在：{key}", f"No such recipe: {key}"))
    return _public(r)


def delete(rid: str) -> None:
    db.execute("DELETE FROM recipes WHERE id=? AND builtin=0", (rid,))


def update(rid: str, **changes) -> dict:
    allowed = {}
    for k in ("title", "description"):
        if k in changes:
            allowed[k] = str(changes[k])[:500]
    if "schedule" in changes:
        allowed["schedule"] = dumps(changes["schedule"]) if changes["schedule"] else None
    if "schedule_params" in changes:
        allowed["schedule_params"] = dumps(changes["schedule_params"] or {})
    if allowed:
        db.execute(f"UPDATE recipes SET {', '.join(f'{k}=?' for k in allowed)} WHERE id=?", (*allowed.values(), rid))
    return get(rid)


# ---------------------------------------------------------------- saving a workflow as a recipe
def from_workflow(detail: dict, title: str) -> dict:
    """Turn a recorded workflow into a recipe: chats become parameters, task ids become references."""
    steps_in = [s for s in detail["steps"] if s["tool"] not in SKIP and s.get("status") != "error"]
    chats: list[str] = []

    def param_for(value: str) -> str:
        if value not in chats:
            chats.append(value)
        return "{chat%d}" % (chats.index(value) + 1)

    producer: dict[str, tuple[int, str]] = {}
    out = []
    for i, s in enumerate(steps_in, 1):
        args = copy.deepcopy(s.get("args") or {})
        for key in ("chat", "chat_a", "chat_b", "intro_chat", "files_chat"):
            if isinstance(args.get(key), str) and args[key]:
                args[key] = param_for(args[key])
        if isinstance(args.get("chats"), list):
            args["chats"] = [param_for(str(c)) for c in args["chats"]]
        if isinstance(args.get("task_ids"), list):
            refs = []
            for tid in args["task_ids"]:
                if tid in producer:
                    n, kind = producer[tid]
                    ref = "{{%d.tasks[*].task_id}}" % n if kind == "many" else "{{%d.task_id}}" % n
                    if ref not in refs:
                        refs.append(ref)
            args["task_ids"] = refs[0] if len(refs) == 1 and "[*]" in refs[0] else refs
        for tid in s.get("task_ids") or []:
            producer[tid] = (i, "many" if s["tool"] == "tg_download" else "one")
        out.append({"tool": s["tool"], "args": args})
    if not out:
        raise ValueError(L("这个工作流没有可以复用的步骤", "This workflow has no reusable steps"))
    rid = uuid.uuid4().hex[:8]
    name = re.sub(r"[^a-z0-9_]+", "_", (title or "recipe").lower()).strip("_")[:40] or f"recipe_{rid}"
    params = [{"name": f"chat{i + 1}", "description": f"Chat (was {c})", "required": True, "default": c}
              for i, c in enumerate(chats)]
    db.upsert("recipes", {"id": rid, "name": f"{name}_{rid[:4]}", "title": title or name, "description": detail["workflow"].get("goal") or "",
                          "steps": dumps(out), "params": dumps(params), "schedule": None, "schedule_params": None,
                          "builtin": 0, "created": time.time(), "last_run": None, "runs": 0})
    return get(rid)


# ---------------------------------------------------------------- running
def _dig(value: Any, path: str) -> Any:
    for part in path.split("."):
        if value is None:
            return None
        m = re.fullmatch(r"(\w+)\[\*\]", part)
        if m:
            value = value.get(m.group(1)) if isinstance(value, dict) else None
            continue
        if isinstance(value, list):
            value = [v.get(part) if isinstance(v, dict) else None for v in value]
        else:
            value = value.get(part) if isinstance(value, dict) else None
    return value


def _resolve(obj: Any, params: dict, results: list) -> Any:
    if isinstance(obj, dict):
        return {k: _resolve(v, params, results) for k, v in obj.items()}
    if isinstance(obj, list):
        out = []
        for v in obj:
            r = _resolve(v, params, results)
            out.extend(r if isinstance(v, str) and _REF.fullmatch(v) and isinstance(r, list) else [r])
        return [x for x in out if x not in (None, "")]
    if not isinstance(obj, str):
        return obj
    m = _REF.fullmatch(obj)
    if m:
        n = int(m.group(1))
        return _dig(results[n - 1] if 0 < n <= len(results) else None, m.group(2))
    text = _PARAM.sub(lambda mm: str(params.get(mm.group(1), "")), obj)
    if text.strip().lstrip("-").isdigit() and _PARAM.search(obj):
        return int(text)
    return text


def _clean(args: dict) -> dict:
    out = {}
    for k, v in args.items():
        if v in ("", None, []):
            continue
        if k in ("types", "extensions") and isinstance(v, str):
            v = [x.strip() for x in v.split(",") if x.strip()]
        out[k] = v
    return out


async def run(key: str, params: dict | None, agent: str = "recipe", background: bool = True) -> dict:
    from .tools import call_tool
    from .workflow import workflows
    r = get(key)
    params = {**{p["name"]: p.get("default", "") for p in r["params"]}, **(params or {})}
    missing = [p["name"] for p in r["params"] if p.get("required") and not str(params.get(p["name"], "")).strip()]
    if missing:
        raise ValueError(L(f"缺少参数：{', '.join(missing)}", f"Missing parameters: {', '.join(missing)}"))
    session = f"recipe:{uuid.uuid4().hex[:8]}"
    shown = ", ".join(f"{k}={v}" for k, v in params.items() if v)
    wf = workflows.start(session, agent, f"{r['title']}" + (f" · {shown}" if shown else ""), r["description"], explicit=True)
    db.execute("UPDATE recipes SET last_run=?, runs=runs+1 WHERE id=?", (time.time(), r["id"]))

    async def go():
        results: list = []
        failed = 0
        for step in r["steps"]:
            args = _clean(_resolve(step["args"], params, results))
            ok, res = await call_tool(step["tool"], args, agent, session, "api")
            results.append(res if ok else None)
            if not ok:
                failed += 1
                break
        workflows.finish(session, L(f"配方完成：{len(results)}/{len(r['steps'])} 步", f"Recipe finished: {len(results)}/{len(r['steps'])} steps")
                         + (L("，有步骤出错", ", a step failed") if failed else ""), "failed" if failed else "done")
        return results

    if background:
        asyncio.create_task(go())
        return {"workflow_id": wf.id, "recipe": r["name"], "params": params, "steps": len(r["steps"]),
                "hint": "Running in the background; the user sees it as a workflow in the console."}
    results = await go()
    return {"workflow_id": wf.id, "recipe": r["name"], "results": results}


# ---------------------------------------------------------------- schedules
def _due(r: dict, now: float) -> bool:
    sch = r.get("schedule") or {}
    last = r.get("last_run") or 0
    if sch.get("every_hours"):
        return now - last >= float(sch["every_hours"]) * 3600
    if sch.get("daily_at"):
        try:
            h, m = map(int, str(sch["daily_at"]).split(":"))
        except ValueError:
            return False
        lt = time.localtime(now)
        target = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, h, m, 0, 0, 0, -1))
        return now >= target and last < target
    return False


async def schedule_loop() -> None:
    from .accounts import manager as accounts
    while True:
        await asyncio.sleep(30)
        if not any(a.status == "ready" for a in accounts.accounts.values()):
            continue
        now = time.time()
        for r in list_recipes():
            if r.get("schedule") and _due(r, now):
                try:
                    await run(r["id"], r.get("schedule_params") or {}, agent="schedule")
                    bus.log("info", "schedule", L(f"定时运行配方：{r['title']}", f"Scheduled recipe: {r['title']}"))
                except Exception as e:
                    db.execute("UPDATE recipes SET last_run=? WHERE id=?", (now, r["id"]))
                    bus.log("error", "schedule", L(f"定时配方失败：{r['title']}", f"Scheduled recipe failed: {r['title']}"), str(e))


# ---------------------------------------------------------------- MCP prompts
GUIDES = [
    {"name": "tg_intro_and_download", "title": "介绍频道 + 下载频道 / Intro channel + download channel",
     "description": "Find items in a channel of descriptions and download the matching files from another channel.",
     "arguments": [("intro_chat", "Channel with the descriptions", True), ("files_chat", "Channel with the files", True),
                   ("what", "What to look for (title, keyword, newest…)", False)],
     "text": ("Use TG Agent. Start with tg_start_workflow. The descriptions are in {intro_chat}; the files are in {files_chat}.\n"
              "1. Read or search {intro_chat} for: {what}. Use tg_file_context on interesting posts to get passwords and versions.\n"
              "2. Make sure {files_chat} is indexed (tg_index_status, else tg_index_chat + tg_wait_tasks).\n"
              "3. Pair posts with files using tg_match_posts; check unclear pairs with tg_search_files.\n"
              "4. If several candidates fit, ask the user with tg_ask_user instead of guessing.\n"
              "5. tg_plan_download, then tg_download and tg_wait_tasks. Report passwords found for the archives.\n"
              "Finish with tg_finish_workflow.")},
]


def prompts() -> list[dict]:
    out = []
    for g in GUIDES:
        out.append({"name": g["name"], "title": g["title"], "description": g["description"],
                    "arguments": [{"name": a, "description": d, "required": req} for a, d, req in g["arguments"]]})
    for r in list_recipes():
        out.append({"name": f"recipe_{r['name']}", "title": r["title"], "description": r["description"] or r["title"],
                    "arguments": [{"name": p["name"], "description": p.get("description", ""), "required": bool(p.get("required"))}
                                  for p in r["params"]]})
    return out


def render_prompt(name: str, args: dict) -> str:
    for g in GUIDES:
        if g["name"] == name:
            vals = {a: args.get(a) or "(ask the user)" for a, _, _ in g["arguments"]}
            return g["text"].format(**vals)
    if name.startswith("recipe_"):
        r = get(name[len("recipe_"):])
        shown = ", ".join(f'"{k}": "{v}"' for k, v in args.items() if v)
        lines = [f"Use TG Agent to run the recipe \"{r['title']}\": {r['description']}",
                 f"Call tg_run_recipe with name=\"{r['name']}\" and params={{{shown}}}, then follow the workflow it starts "
                 "(tg_tasks / tg_wait_tasks) and report the outcome. Steps of the recipe:"]
        lines += [f"  {i}. {s['tool']} {dumps(s['args'])}" for i, s in enumerate(r["steps"], 1)]
        return "\n".join(lines)
    raise ValueError(f"Unknown prompt: {name}")
