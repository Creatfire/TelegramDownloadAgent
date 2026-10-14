"""Workflow reports and re-runs, and the GitHub release check."""
from __future__ import annotations

import asyncio
import json
import time
import uuid

import httpx

from . import __version__
from .activity import bus
from .config import settings
from .i18n import L
from .readers import human_size
from .workflow import POLL_TOOLS, workflows

REPO = "Creatfire/TelegramDownloadAgent"
SKIP_ON_RERUN = POLL_TOOLS | {"tg_start_workflow", "tg_finish_workflow", "tg_task_control"}


# ---------------------------------------------------------------- reports
def _fmt_time(ts: float | None) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)) if ts else "—"


def workflow_report(wf_id: str, tasks: list[dict]) -> str:
    d = workflows.detail(wf_id)
    if not d:
        raise ValueError("not found")
    w, steps = d["workflow"], d["steps"]
    end = w.get("ended") or w.get("updated") or time.time()
    lines = [f"# {w['title']}", "",
             f"- Agent: `{w['agent']}`",
             f"- Status: **{w['status']}**",
             f"- Started: {_fmt_time(w['created'])}  ·  Duration: {int(end - w['created'])}s  ·  Steps: {len(steps)}"]
    if w.get("goal"):
        lines += ["", f"> {w['goal']}"]
    if w.get("summary"):
        lines += ["", "**Summary:** " + w["summary"]]
    lines += ["", "## Steps", ""]
    by_step: dict[str, list[dict]] = {}
    for t in tasks:
        by_step.setdefault(t.get("step_id", ""), []).append(t)
    for s in steps:
        deps = [p for p in s.get("parents", []) if p.get("kind") == "data"]
        seqs = {x["id"]: x["seq"] for x in steps}
        lines.append(f"### {s['seq']}. `{s['tool']}`" + (f"  · uses step {', '.join(str(seqs.get(p['id'], '?')) for p in deps)}" if deps else ""))
        args = {k: v for k, v in (s.get("args") or {}).items() if v not in (None, "", [], False)}
        if args:
            lines.append(f"- Args: `{json.dumps(args, ensure_ascii=False)}`")
        if s.get("status") == "error":
            lines.append(f"- **Error:** {s.get('error')}")
        elif s.get("summary"):
            lines.append(f"- Result: {s['summary']}")
        if s.get("polls"):
            lines.append(f"- Progress checked ×{s['polls']}")
        for t in by_step.get(s["id"], [])[:50]:
            lines.append(f"  - {t['title']} — {t['status']} · {human_size(t.get('total', 0))}")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------- re-run
async def rerun_workflow(wf_id: str) -> dict:
    """Replay a workflow's tool calls in order as a new workflow (agent "replay").
    Downloads go through the normal approval rules; polls and task control are skipped."""
    from .tools import call_tool
    d = workflows.detail(wf_id)
    if not d:
        raise ValueError("not found")
    session = f"replay:{uuid.uuid4().hex[:8]}"
    steps = [s for s in d["steps"] if s["tool"] not in SKIP_ON_RERUN]
    new = workflows.start(session, "replay", L("重跑：", "Re-run: ") + d["workflow"]["title"],
                          d["workflow"].get("goal", ""), explicit=True)

    async def run():
        failed = 0
        for s in steps:
            ok, _ = await call_tool(s["tool"], s.get("args") or {}, "replay", session, "api")
            failed += 0 if ok else 1
        workflows.finish(session, L(f"重跑完成：{len(steps)} 步，{failed} 步出错", f"Re-run finished: {len(steps)} steps, {failed} failed"),
                         "failed" if failed else "done")

    asyncio.create_task(run())
    return {"workflow_id": new.id, "steps": len(steps)}


# ---------------------------------------------------------------- update check
latest: dict = {}


def _vtuple(v: str) -> tuple:
    out = []
    for p in v.lstrip("vV").split("."):
        num = "".join(ch for ch in p if ch.isdigit())
        out.append(int(num) if num else 0)
    return tuple(out)


def _proxy_url() -> str | None:
    p = settings.get("default_proxy") or {}
    if p.get("type") in ("socks5", "http") and p.get("host"):
        scheme = "socks5" if p["type"] == "socks5" else "http"
        return f"{scheme}://{p['host']}:{p['port']}"
    return None


async def check_updates_once() -> dict:
    url = f"https://api.github.com/repos/{REPO}/releases/latest"
    for proxy in (_proxy_url(), None):
        try:
            async with httpx.AsyncClient(timeout=15, proxy=proxy, headers={"Accept": "application/vnd.github+json"}) as c:
                r = await c.get(url)
            if r.status_code == 404:
                return {}
            r.raise_for_status()
            data = r.json()
            tag = data.get("tag_name", "")
            info = {"version": tag.lstrip("vV"), "url": data.get("html_url"), "name": data.get("name") or tag,
                    "newer": _vtuple(tag) > _vtuple(__version__), "checked": time.time()}
            latest.clear()
            latest.update(info)
            return info
        except Exception:
            continue
    return {}


async def update_loop() -> None:
    await asyncio.sleep(15)
    announced = ""
    while True:
        if settings.get("check_updates"):
            info = await check_updates_once()
            if info.get("newer") and info["version"] != announced:
                announced = info["version"]
                bus.log("info", "system", L(f"有新版本 v{info['version']}", f"New version v{info['version']} available"),
                        info.get("url") or "")
                bus.emit("update", info)
        await asyncio.sleep(24 * 3600)
