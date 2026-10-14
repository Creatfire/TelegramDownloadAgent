"""Main service: REST API, SSE live events, the web console and the embedded MCP endpoint (/mcp)."""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, auth, extras, secure
from .accounts import AccountError, manager as accounts
from .activity import bus
from .config import DATA_DIR, EXPORTS_DIR, PORT, ROOT, WEB_DIR, settings
from .i18n import L
from .mcp_server import build_direct_server, tool_dicts
from .tasks import get_tasks
from .tools import call_tool
from .watch import watches
from .workflow import workflows

mcp_srv = build_direct_server()
mcp_app = mcp_srv.streamable_http_app(streamable_http_path="/mcp", host="127.0.0.1")


@asynccontextmanager
async def lifespan(app: FastAPI):
    tm = get_tasks()
    workflows.close_stale_on_startup()
    bus.log("info", "system", f"TG Agent {__version__}", f"http://127.0.0.1:{PORT}")
    if secure.WEAK_STORAGE:
        bus.log("warn", "system", L("未找到系统钥匙串", "No system keychain"),
                L("api_hash 仅做了编码存储", "api_hash is only obfuscated on disk"))
    bg = [asyncio.create_task(accounts.connect_all()), asyncio.create_task(tm.run_forever()),
          asyncio.create_task(watches.run_forever()), asyncio.create_task(extras.update_loop())]
    async with mcp_srv.session_manager.run():
        yield
    for t in bg:
        t.cancel()
    await tm.shutdown()
    await accounts.shutdown()


app = FastAPI(title="TG Agent", version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None)
for r in mcp_app.routes:
    app.router.routes.append(r)

_ALLOWED_HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}", f"[::1]:{PORT}"}
_PUBLIC = ("/assets/", "/favicon")


def _request_token(request: Request) -> tuple[str | None, str]:
    h = request.headers.get("authorization", "")
    if h.lower().startswith("bearer "):
        return h[7:].strip(), "bearer"
    if request.headers.get("x-tga-token"):
        return request.headers["x-tga-token"], "bearer"
    return request.cookies.get(auth.COOKIE), "cookie"


@app.middleware("http")
async def guard(request: Request, call_next):
    # Only local Host headers (DNS-rebinding protection)
    if request.headers.get("host", "") not in _ALLOWED_HOSTS:
        return JSONResponse({"error": "forbidden host"}, status_code=403)
    path = request.url.path
    # Opening the link printed at startup (/?token=…) stores the token in a cookie
    if path == "/" and request.query_params.get("token"):
        if not auth.check(request.query_params["token"]):
            return JSONResponse({"error": "invalid token"}, status_code=401)
        resp = RedirectResponse("/", status_code=303)
        resp.set_cookie(auth.COOKIE, request.query_params["token"], httponly=True, samesite="strict", max_age=3600 * 24 * 365)
        return resp
    if path == "/" or path.startswith(_PUBLIC) or path == "/api/login":
        return await call_next(request)
    token, how = _request_token(request)
    if not auth.check(token):
        return JSONResponse({"error": "unauthorized", "hint": "Open the console link printed by TG Agent, or send "
                                                               "'Authorization: Bearer <token>'."}, status_code=401)
    # Cookie-authenticated writes must also carry a custom header (blocks cross-site form posts)
    if how == "cookie" and request.method in ("POST", "PATCH", "DELETE", "PUT") and request.headers.get("x-tga") != "1":
        return JSONResponse({"error": "missing X-TGA header"}, status_code=403)
    return await call_next(request)


def _agent(request: Request) -> tuple[str, str, str]:
    """(agent name, session id, transport) of a REST caller."""
    raw = request.headers.get("x-agent", "")
    try:
        name = bytes.fromhex(raw).decode("utf-8") if raw else ""
    except ValueError:
        name = raw
    session = request.headers.get("x-session", "")
    if not name or name == "console":
        return "console", "console", "console"
    return name, session or f"api:{name}", "stdio" if session.startswith("stdio:") else "api"


async def _acc(coro):
    try:
        acc = await coro
        return acc.public() if hasattr(acc, "public") else acc
    except AccountError as e:
        raise HTTPException(400, str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"{type(e).__name__}: {e}")


# ---------------------------------------------------------------- auth
@app.post("/api/login")
async def api_login(body: dict):
    if not auth.check(str(body.get("token", "")).strip()):
        raise HTTPException(401, "invalid token")
    resp = JSONResponse({"ok": True})
    resp.set_cookie(auth.COOKIE, body["token"].strip(), httponly=True, samesite="strict", max_age=3600 * 24 * 365)
    return resp


@app.get("/api/token")
async def api_token():
    return {"token": auth.get_token()}


@app.post("/api/token/regenerate")
async def api_token_regen():
    tok = auth.regenerate()
    resp = JSONResponse({"token": tok})
    resp.set_cookie(auth.COOKIE, tok, httponly=True, samesite="strict", max_age=3600 * 24 * 365)
    bus.log("warn", "console", L("访问令牌已更换", "Access token regenerated"),
            L("已接入的 AI 客户端需要更新配置", "Update the token in your AI clients"))
    return resp


# ---------------------------------------------------------------- tools
@app.get("/api/tools")
async def api_tools():
    return tool_dicts()


@app.post("/api/tools/{name}")
async def api_call(name: str, request: Request):
    try:
        args = await request.json()
    except Exception:
        args = {}
    agent, session, transport = _agent(request)
    ok, result = await call_tool(name, args if isinstance(args, dict) else {}, agent, session, transport)
    return {"ok": True, "result": result} if ok else {"ok": False, "error": result}


# ---------------------------------------------------------------- state and events
@app.get("/api/state")
async def api_state():
    tm = get_tasks()
    return {
        "version": __version__, "port": PORT, "platform": sys.platform,
        "accounts": accounts.list(), "settings": settings.all(),
        "stats": tm.stats(), "tasks": tm.list(limit=400), "approvals": tm.approvals(),
        "activity": list(bus.recent)[-200:], "workflows": workflows.list(150), "watches": watches.list(),
        "update": extras.latest,
        "paths": {"root": str(ROOT), "data": str(DATA_DIR), "exports": str(EXPORTS_DIR), "checkout": (ROOT / "mcp_stdio.py").exists(), "frozen": bool(getattr(sys, "frozen", False)),
                  "python": sys.executable},
    }


@app.get("/api/events")
async def api_events(request: Request):
    q = bus.subscribe()

    async def gen():
        try:
            yield "retry: 2000\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15)
                    yield f"event: {ev['kind']}\ndata: {json.dumps(ev['data'], ensure_ascii=False, default=str)}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            bus.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


# ---------------------------------------------------------------- workflows
@app.get("/api/workflows")
async def api_workflows(limit: int = 150):
    return workflows.list(limit)


@app.get("/api/workflows/{wf_id}")
async def api_workflow(wf_id: str):
    d = workflows.detail(wf_id)
    if not d:
        raise HTTPException(404, "not found")
    tm = get_tasks()
    ids = {tid for s in d["steps"] for tid in s.get("task_ids", [])}
    d["tasks"] = [t.public() for t in tm.tasks.values() if t.id in ids or t.workflow_id == wf_id]
    return d


@app.get("/api/steps/{step_id}")
async def api_step(step_id: str):
    s = workflows.step_result(step_id)
    if not s:
        raise HTTPException(404, "not found")
    return s


@app.get("/api/workflows/{wf_id}/report")
async def api_workflow_report(wf_id: str):
    tm = get_tasks()
    tasks = [t.public() for t in tm.tasks.values() if t.workflow_id == wf_id]
    try:
        md = extras.workflow_report(wf_id, tasks)
    except ValueError:
        raise HTTPException(404, "not found")
    return PlainTextResponse(md, media_type="text/markdown; charset=utf-8")


@app.post("/api/workflows/{wf_id}/rerun")
async def api_workflow_rerun(wf_id: str):
    try:
        return await extras.rerun_workflow(wf_id)
    except ValueError:
        raise HTTPException(404, "not found")


@app.post("/api/update/check")
async def api_update_check():
    return await extras.check_updates_once() or {"error": "unavailable"}


@app.patch("/api/workflows/{wf_id}")
async def api_workflow_rename(wf_id: str, body: dict):
    workflows.rename(wf_id, str(body.get("title", "")).strip() or "—")
    return {"ok": True}


@app.delete("/api/workflows/{wf_id}")
async def api_workflow_delete(wf_id: str):
    workflows.delete(wf_id)
    return {"ok": True}


# ---------------------------------------------------------------- approvals
@app.get("/api/approvals")
async def api_approvals():
    return get_tasks().approvals()


@app.post("/api/approvals/{batch}")
async def api_approve(batch: str, body: dict):
    return get_tasks().approve(batch, bool(body.get("approve")))


# ---------------------------------------------------------------- watches
@app.get("/api/watches")
async def api_watches():
    return watches.list()


@app.post("/api/watches")
async def api_watch_add(body: dict):
    if not body.get("chat"):
        raise HTTPException(400, "chat is required")
    return await _acc(watches.add(body.get("account"), body["chat"], "console", body.get("filters") or {},
                                  body.get("interval_min", 30), body.get("subdir", ""), body.get("include_recent", 0)))


@app.patch("/api/watches/{wid}")
async def api_watch_update(wid: str, body: dict):
    try:
        return watches.update(wid, **body)
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.delete("/api/watches/{wid}")
async def api_watch_remove(wid: str):
    watches.remove(wid)
    return {"ok": True}


@app.post("/api/watches/{wid}/check")
async def api_watch_check(wid: str):
    return await _acc(watches.check(wid))


# ---------------------------------------------------------------- accounts
@app.get("/api/accounts")
async def api_accounts():
    return accounts.list()


@app.post("/api/accounts")
async def api_add_account(body: dict):
    for k in ("api_id", "api_hash"):
        if not str(body.get(k, "")).strip():
            raise HTTPException(400, f"{k} is required")
    try:
        acc = accounts.add(body.get("name") or body.get("phone") or "account", int(body["api_id"]), body["api_hash"],
                           body.get("phone", ""), body.get("proxy"))
    except ValueError:
        raise HTTPException(400, "api_id must be a number")
    asyncio.create_task(accounts.connect(acc.id))
    return acc.public()


@app.patch("/api/accounts/{acc_id}")
async def api_update_account(acc_id: str, body: dict):
    return await _acc(accounts.update(acc_id, body))


@app.delete("/api/accounts/{acc_id}")
async def api_remove_account(acc_id: str, logout: bool = False):
    await _acc(accounts.remove(acc_id, logout))
    return {"ok": True}


@app.post("/api/accounts/{acc_id}/connect")
async def api_connect(acc_id: str):
    return await _acc(accounts.connect(acc_id))


@app.post("/api/accounts/{acc_id}/send_code")
async def api_send_code(acc_id: str):
    return await _acc(accounts.send_code(acc_id))


@app.post("/api/accounts/{acc_id}/code")
async def api_code(acc_id: str, body: dict):
    return await _acc(accounts.submit_code(acc_id, str(body.get("code", ""))))


@app.post("/api/accounts/{acc_id}/password")
async def api_password(acc_id: str, body: dict):
    return await _acc(accounts.submit_password(acc_id, str(body.get("password", ""))))


@app.post("/api/accounts/{acc_id}/qr")
async def api_qr(acc_id: str):
    return await _acc(accounts.qr_start(acc_id))


@app.get("/api/accounts/{acc_id}/qr")
async def api_qr_current(acc_id: str):
    from .accounts import qr_svg
    acc = accounts.get(acc_id)
    if acc.status == "qr_waiting" and acc.qr is not None:
        return {"status": acc.status, "expires": acc.qr.expires.timestamp(), "svg": qr_svg(acc.qr.url)}
    return {"status": acc.status, "error": acc.error}


@app.post("/api/accounts/{acc_id}/default")
async def api_default(acc_id: str):
    accounts.get(acc_id)
    settings.update({"default_account": acc_id})
    return {"ok": True}


# ---------------------------------------------------------------- settings, tasks, files
@app.get("/api/settings")
async def api_settings():
    return settings.all()


@app.post("/api/settings")
async def api_save_settings(body: dict):
    for k in ("max_concurrent_files", "connections_per_file", "part_size_kb", "approval_files"):
        if k in body:
            body[k] = max(0 if k == "approval_files" else 1, int(body[k]))
    if "connections_per_file" in body:
        body["connections_per_file"] = min(body["connections_per_file"], 16)
    if "max_concurrent_files" in body:
        body["max_concurrent_files"] = min(body["max_concurrent_files"], 8)
    if "speed_limit_kbps" in body:
        body["speed_limit_kbps"] = max(0, int(body["speed_limit_kbps"] or 0))
    for k in ("read_wait_time", "approval_size_gb"):
        if k in body:
            body[k] = max(0.0, float(body[k]))
    s = settings.update(body)
    bus.log("info", "console", L("设置已更新", "Settings saved"), ", ".join(body))
    get_tasks()._wake.set()
    return s


@app.post("/api/tasks/control")
async def api_task_control(body: dict):
    return await get_tasks().control(body.get("action", ""), body.get("task_ids"), bool(body.get("all")), "console")


@app.post("/api/open")
async def api_open(body: dict):
    """Reveal a file or folder inside the download or export directory."""
    p = Path(body.get("path") or settings.get("download_dir")).resolve()
    roots = [Path(settings.get("download_dir")).resolve(), EXPORTS_DIR.resolve()]
    if not any(p == r or r in p.parents for r in roots):
        raise HTTPException(400, "Only paths inside the download or export directory can be opened")
    target = p if p.is_dir() else p.parent
    target.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        if p.is_file():
            subprocess.Popen(["explorer", "/select,", str(p)])
        else:
            os.startfile(str(target))
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(p)] if p.is_file() else ["open", str(target)])
    else:
        subprocess.Popen(["xdg-open", str(target)])
    return {"ok": True}


# ---------------------------------------------------------------- static
app.mount("/assets", StaticFiles(directory=WEB_DIR), name="assets")


@app.get("/")
async def index():
    return FileResponse(WEB_DIR / "index.html", headers={"Cache-Control": "no-cache"})
