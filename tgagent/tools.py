"""Agent tool registry, shared by MCP (HTTP and stdio bridge) and the console's REST API.
Every call is recorded as a step of a workflow so the user can follow it live."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from telethon.errors import FloodWaitError, RPCError

from . import index, readers
from .accounts import AccountError, manager as accounts
from .activity import bus
from .config import settings
from .i18n import L, lang
from .tasks import get_tasks
from .watch import watches
from .workflow import current_step, progress_reporter, workflows

ACCOUNT = {"type": "string", "description": "Account id (see tg_list_accounts). Defaults to the default account."}
CHAT = {"type": "string", "description": "Chat: @username, username, t.me link, t.me/c/<id> link, or numeric id such as -100123…"}
FILE_FILTERS = {
    "types": {"type": "array", "items": {"type": "string", "enum": ["document", "video", "audio", "photo", "voice", "gif", "round", "sticker"]},
              "description": "File kinds. Default: everything except stickers."},
    "name_contains": {"type": "string", "description": "File name or caption contains (case-insensitive)."},
    "extensions": {"type": "array", "items": {"type": "string"}, "description": "Extensions, e.g. [\"zip\", \"mp4\"]."},
    "min_size_mb": {"type": "number"},
    "max_size_mb": {"type": "number"},
    "since": {"type": "string", "description": "Start date, ISO (e.g. 2025-01-01)."},
    "until": {"type": "string", "description": "End date, ISO."},
}
FILTER_KEYS = list(FILE_FILTERS)


@dataclass
class Tool:
    name: str
    title_zh: str
    title_en: str
    description: str
    schema: dict
    handler: Callable[[dict, "Ctx"], Awaitable[Any]]
    summarize: Callable[[Any], str] = lambda r: ""
    read_only: bool = True
    tracked: bool = True       # recorded as a workflow step

    @property
    def title(self) -> str:
        return self.title_zh if lang() == "zh" else self.title_en

    def input_schema(self) -> dict:
        return {"type": "object", "properties": self.schema.get("properties", {}),
                "required": self.schema.get("required", []), "additionalProperties": False}


@dataclass
class Ctx:
    source: str          # agent name
    session_id: str
    transport: str


def _pick(args: dict, keys: list[str]) -> dict:
    return {k: args[k] for k in keys if args.get(k) not in (None, "", [])}


def _filters(args: dict) -> dict:
    f = _pick(args, FILTER_KEYS)
    if "types" in f:
        f["types_"] = f.pop("types")
    return f


async def _client(args: dict):
    return await accounts.client(args.get("account"))


async def _chat_id(args: dict, key: str = "chat") -> int:
    _, c = await _client(args)
    return readers.utils.get_peer_id(await readers.get_entity(c, args[key]))


# ---------------------------------------------------------------- handlers

async def h_start(args, ctx: Ctx):
    wf = workflows.start(ctx.session_id, ctx.source, args.get("title", ""), args.get("goal", ""), explicit=True)
    return {"workflow_id": wf.id, "title": wf.title,
            "note": "Workflow started. Every following call is shown under it. Call tg_finish_workflow when the request is done."}


async def h_finish(args, ctx: Ctx):
    wf = workflows.finish(ctx.session_id, args.get("summary", ""), args.get("status", "done"))
    if not wf:
        return {"note": "No active workflow in this session."}
    return {"workflow_id": wf.id, "status": wf.status, "steps": len(wf.steps)}


async def h_accounts(args, ctx):
    return {"default_account": settings.get("default_account"), "accounts": accounts.list(),
            "note": "Accounts with status=ready can be used; others need the user to log in in the web console."}


async def h_dialogs(args, ctx):
    _, c = await _client(args)
    return await readers.list_dialogs(c, args.get("kind", "all"), args.get("query", ""), args.get("limit", 100))


async def h_resolve(args, ctx):
    _, c = await _client(args)
    return await readers.resolve_chat(c, args["chat"])


async def h_messages(args, ctx):
    _, c = await _client(args)
    return await readers.get_messages(c, args["chat"], **_pick(args, [
        "limit", "offset_id", "min_id", "max_id", "since", "until", "query", "media_only", "oldest_first", "text_max"]))


async def h_search(args, ctx):
    _, c = await _client(args)
    return await readers.search_messages(c, args["query"], args.get("chat"), args.get("limit", 30))


async def h_message(args, ctx):
    _, c = await _client(args)
    return await readers.get_message(c, args.get("link"), args.get("chat"), args.get("message_id"))


async def h_files(args, ctx):
    _, c = await _client(args)
    return await readers.list_files(c, args["chat"], **_pick(args, ["limit", "offset_id", "oldest_first", "scan_limit"]),
                                    **_filters(args))


async def h_export(args, ctx):
    return await get_tasks().start_export(args.get("account"), ctx.source, args["chat"], args.get("what", "files"),
                                          args.get("format", "csv"), args.get("limit"), bool(args.get("oldest_first")),
                                          **_filters(args))


async def h_download(args, ctx):
    if not args.get("links") and not args.get("chat"):
        raise ValueError("Provide links, or chat (optionally with message_ids or filters).")
    return await get_tasks().enqueue_downloads(args.get("account"), ctx.source, subdir=args.get("subdir", ""),
                                               **_dl_request(args))


def _dl_request(args: dict) -> dict:
    return dict(links=args.get("links"), chat=args.get("chat"), message_ids=args.get("message_ids"),
                limit=args.get("limit", 50), oldest_first=bool(args.get("oldest_first")),
                include_album=bool(args.get("include_album")),
                complete_archives=args.get("complete_archives", True), **_filters(args))


async def h_plan(args, ctx):
    if not args.get("links") and not args.get("chat"):
        raise ValueError("Provide links, or chat (optionally with message_ids or filters).")
    return await get_tasks().plan_download(args.get("account"), ctx.source, **_dl_request(args))


async def h_wait(args, ctx):
    return await get_tasks().wait_tasks(args.get("task_ids") or [], args.get("timeout_s", 120), progress_reporter.get())


async def h_tasks(args, ctx):
    tm = get_tasks()
    items = tm.list(args.get("status", "all"), args.get("task_ids"), args.get("kind"), args.get("limit", 30))
    st = tm.stats()
    return {"stats": {**st, "speed_human": readers.human_size(st["speed"]) + "/s",
                      "remaining_human": readers.human_size(st["remaining_bytes"])},
            "pending_approvals": tm.approvals(), "tasks": items}


async def h_control(args, ctx):
    return await get_tasks().control(args["action"], args.get("task_ids"), bool(args.get("all")), ctx.source)


async def h_index_chat(args, ctx):
    return await get_tasks().start_index(args.get("account"), ctx.source, args["chat"], bool(args.get("full")))


async def h_index_status(args, ctx):
    rows = index.status(args.get("account"))
    return {"chats": [{**r, "total_size_human": readers.human_size(r["total_size"] or 0)} for r in rows],
            "note": "full_scan=1 means the whole chat has been indexed; otherwise only files seen so far are known."}


async def h_search_files(args, ctx):
    chat_ids = []
    for ch in args.get("chats", []) or []:
        _, c = await _client(args)
        chat_ids.append(readers.utils.get_peer_id(await readers.get_entity(c, ch)))
    mb = 1024 * 1024
    res = index.search(args.get("account"), args.get("query", ""), chat_ids or None, args.get("types"),
                       args.get("extensions"), int(args["min_size_mb"] * mb) if args.get("min_size_mb") else None,
                       int(args["max_size_mb"] * mb) if args.get("max_size_mb") else None,
                       args.get("sort", "date"), args.get("limit", 50))
    res["total_size_human"] = readers.human_size(res["total_size"])
    res["note"] = "Searched the local index only (no Telegram requests). Use tg_index_chat to index more chats."
    return res


async def h_compare(args, ctx):
    a = await _chat_id(args, "chat_a")
    b = await _chat_id(args, "chat_b")
    res = index.compare(args.get("account"), a, b, args.get("by", "name_size"), args.get("sample", 30))
    for k in ("in_both", "only_in_a", "only_in_b"):
        res[k]["size_human"] = readers.human_size(res[k]["size"])
    res["note"] = "Compared from the local index. Index both chats fully (tg_index_chat) for complete results."
    return res


async def h_watch(args, ctx):
    action = args.get("action", "list")
    if action == "list":
        return {"watches": watches.list()}
    if action == "add":
        if not args.get("chat"):
            raise ValueError("chat is required")
        filters = {k: args[k] for k in ("types", "name_contains", "extensions", "min_size_mb", "max_size_mb") if args.get(k)}
        return await watches.add(args.get("account"), args["chat"], ctx.source, filters,
                                 args.get("interval_min", 30), args.get("subdir", ""), args.get("include_recent", 0))
    if not args.get("watch_id"):
        raise ValueError("watch_id is required")
    if action == "remove":
        watches.remove(args["watch_id"])
        return {"removed": args["watch_id"]}
    if action in ("pause", "resume"):
        w = watches.get(args["watch_id"])
        if w["pending_approval"]:
            raise ValueError("This watch is waiting for the user's approval in the console.")
        return watches.update(args["watch_id"], enabled=action == "resume")
    if action == "check":
        return await watches.check(args["watch_id"])
    raise ValueError(f"Unknown action: {action}")


DL_SUMMARY = lambda r: (L(f"待批准 {r['awaiting_approval']} 个 · {r['total_size_human']}",
                          f"{r['awaiting_approval']} awaiting approval · {r['total_size_human']}")
                        if r.get("requires_approval") else
                        L(f"入队 {r['queued']} 个 · {r['total_size_human']}", f"{r['queued']} queued · {r['total_size_human']}"))

TOOLS: list[Tool] = [
    Tool("tg_start_workflow", "开始工作流", "Start workflow",
         "Call this FIRST for every new user request, before any other tg_* tool, with a short title describing the "
         "request (in the user's language). The user watches your calls grouped under this workflow in the TG Agent "
         "console. Starting a new workflow closes the previous one.",
         {"properties": {"title": {"type": "string", "description": "Short title, e.g. 'Download new videos from @telegram'"},
                         "goal": {"type": "string", "description": "Optional: what the user asked for, in one or two sentences"}},
          "required": ["title"]},
         h_start, lambda r: r.get("title", ""), tracked=False),
    Tool("tg_finish_workflow", "结束工作流", "Finish workflow",
         "Call this when you have finished the user's request, with a one-sentence summary of the outcome.",
         {"properties": {"summary": {"type": "string"},
                         "status": {"type": "string", "enum": ["done", "failed", "canceled"], "default": "done"}}},
         h_finish, lambda r: r.get("status", ""), tracked=False),
    Tool("tg_list_accounts", "列出账号", "List accounts",
         "List configured Telegram accounts and their login status.",
         {}, h_accounts, lambda r: L(f"{len(r['accounts'])} 个账号", f"{len(r['accounts'])} account(s)")),
    Tool("tg_list_dialogs", "列出对话", "List dialogs",
         "List the channels, groups and private chats the account has joined (including private channels).",
         {"properties": {"account": ACCOUNT,
                         "kind": {"type": "string", "enum": ["all", "channels", "groups", "users"], "default": "all"},
                         "query": {"type": "string", "description": "Filter by title or username"},
                         "limit": {"type": "integer", "default": 100, "maximum": 500}}},
         h_dialogs, lambda r: L(f"{r['count']} 个对话", f"{r['count']} dialogs")),
    Tool("tg_resolve_chat", "解析频道", "Resolve chat",
         "Resolve a chat or link: id, title, about, member count, public or not, joined or not, latest message id. "
         "Also inspects invite links (t.me/+xxx) without joining.",
         {"properties": {"account": ACCOUNT, "chat": CHAT}, "required": ["chat"]},
         h_resolve, lambda r: r.get("title", "")),
    Tool("tg_get_messages", "读取消息", "Read messages",
         "Read a chat's history (newest first by default). Page with offset_id=next_offset_id. Supports date range, "
         "id range, keyword and media-only.",
         {"properties": {"account": ACCOUNT, "chat": CHAT,
                         "limit": {"type": "integer", "default": 30, "maximum": 200},
                         "offset_id": {"type": "integer", "description": "Continue after this id (paging cursor)"},
                         "min_id": {"type": "integer"}, "max_id": {"type": "integer"},
                         "since": {"type": "string"}, "until": {"type": "string"},
                         "query": {"type": "string", "description": "Keyword search"},
                         "media_only": {"type": "boolean"},
                         "oldest_first": {"type": "boolean"},
                         "text_max": {"type": "integer", "default": 500, "description": "Max characters per message text"}},
          "required": ["chat"]},
         h_messages, lambda r: L(f"{r['chat']['title']} · {r['count']} 条消息", f"{r['chat']['title']} · {r['count']} messages")),
    Tool("tg_search_messages", "搜索消息", "Search messages",
         "Keyword search in one chat (if chat is given) or across all joined chats.",
         {"properties": {"account": ACCOUNT, "query": {"type": "string"}, "chat": CHAT,
                         "limit": {"type": "integer", "default": 30, "maximum": 100}},
          "required": ["query"]},
         h_search, lambda r: L(f"{r['count']} 条结果", f"{r['count']} results")),
    Tool("tg_get_message", "读取单条消息", "Read message",
         "Full content and file details of one message (albums include their other items). Pass link "
         "(e.g. https://t.me/name/123) or chat + message_id.",
         {"properties": {"account": ACCOUNT, "link": {"type": "string"}, "chat": CHAT, "message_id": {"type": "integer"}}},
         h_message, lambda r: f"#{r.get('id')} {(r.get('file') or {}).get('name', '')}"),
    Tool("tg_list_files", "列出文件", "List files",
         "List files in a chat (metadata only: name, size, kind, date, link) with filters, plus count and total size. "
         "Scans up to 5000 messages per call; continue with next_offset_id. Files seen are also saved to the local "
         "index. For a complete list of a big chat use tg_index_chat or tg_export.",
         {"properties": {"account": ACCOUNT, "chat": CHAT, **FILE_FILTERS,
                         "limit": {"type": "integer", "default": 100, "maximum": 1000},
                         "offset_id": {"type": "integer"},
                         "oldest_first": {"type": "boolean"},
                         "scan_limit": {"type": "integer", "default": 5000, "description": "Max messages to scan"}},
          "required": ["chat"]},
         h_files, lambda r: L(f"{r['chat']['title']} · {r['count']} 个文件 · {r['total_size_human']}",
                              f"{r['chat']['title']} · {r['count']} files · {r['total_size_human']}")),
    Tool("tg_export", "导出清单", "Export",
         "Export a chat's complete file list (what=files) or message history (what=messages) to csv/json/jsonl/md in "
         "the background. Returns task_id and output_path; read the file when the task is done.",
         {"properties": {"account": ACCOUNT, "chat": CHAT,
                         "what": {"type": "string", "enum": ["files", "messages"], "default": "files"},
                         "format": {"type": "string", "enum": ["csv", "json", "jsonl", "md"], "default": "csv"},
                         "limit": {"type": "integer", "description": "Max rows; omit for all"},
                         "oldest_first": {"type": "boolean"}, **FILE_FILTERS},
          "required": ["chat"]},
         h_export, lambda r: r.get("output_path", ""), read_only=False),
    Tool("tg_download", "下载文件", "Download",
         "Queue files for download (parallel connections, resumable) and return task ids immediately. Three ways: "
         "1) links=[message links]; 2) chat + message_ids; 3) chat + filters + limit (batch). Large batches above the "
         "user's limit wait for approval in the console (the result says requires_approval). Check size first with "
         "tg_list_files.",
         {"properties": {"account": ACCOUNT,
                         "links": {"type": "array", "items": {"type": "string"}, "description": "Message links"},
                         "chat": CHAT,
                         "message_ids": {"type": "array", "items": {"type": "integer"}},
                         **FILE_FILTERS,
                         "limit": {"type": "integer", "default": 50, "maximum": 5000, "description": "Max files when downloading by filter"},
                         "oldest_first": {"type": "boolean"},
                         "include_album": {"type": "boolean", "description": "Also download the other items of albums"},
                         "complete_archives": {"type": "boolean", "default": True,
                                               "description": "For split archives (x.7z.001, x.part1.rar…) also queue the other volumes"},
                         "subdir": {"type": "string", "description": "Sub-folder under the download directory"}}},
         h_download, DL_SUMMARY, read_only=False),
    Tool("tg_plan_download", "下载预估", "Plan download",
         "Dry run of tg_download with the same arguments: how many files, total size, split-archive sets (and missing "
         "volumes), files already downloaded elsewhere, whether approval will be needed, and an estimated duration. "
         "Nothing is queued. Use it before large downloads.",
         {"properties": {"account": ACCOUNT,
                         "links": {"type": "array", "items": {"type": "string"}},
                         "chat": CHAT, "message_ids": {"type": "array", "items": {"type": "integer"}},
                         **FILE_FILTERS,
                         "limit": {"type": "integer", "default": 50, "maximum": 5000},
                         "oldest_first": {"type": "boolean"}, "include_album": {"type": "boolean"},
                         "complete_archives": {"type": "boolean", "default": True}}},
         h_plan, lambda r: L(f"{r['file_count']} 个文件 · {r['total_size_human']}", f"{r['file_count']} files · {r['total_size_human']}")),
    Tool("tg_wait_tasks", "等待任务", "Wait for tasks",
         "Wait until the given tasks finish (or need the user's approval), up to timeout_s, and return their final "
         "state. Sends progress notifications when the client supports them. Use this instead of polling tg_tasks.",
         {"properties": {"task_ids": {"type": "array", "items": {"type": "string"}},
                         "timeout_s": {"type": "integer", "default": 120, "maximum": 1800}},
          "required": ["task_ids"]},
         h_wait, lambda r: ", ".join(f"{k}×{v}" for k, v in r["counts"].items())),
    Tool("tg_tasks", "查看任务", "Tasks",
         "Status, progress, speed and ETA of download/export/index tasks, overall stats, and batches waiting for approval.",
         {"properties": {"status": {"type": "string", "enum": ["all", "active", "approval", "queued", "running", "paused", "done", "failed", "canceled", "skipped"], "default": "all"},
                         "task_ids": {"type": "array", "items": {"type": "string"}},
                         "kind": {"type": "string", "enum": ["download", "export", "index"]},
                         "limit": {"type": "integer", "default": 30}}},
         h_tasks, lambda r: L(f"{len(r['tasks'])} 个任务 · {r['stats']['speed_human']}", f"{len(r['tasks'])} tasks · {r['stats']['speed_human']}")),
    Tool("tg_task_control", "控制任务", "Control tasks",
         "Pause, resume, retry, cancel or remove tasks by task_ids, or all=true for every applicable task.",
         {"properties": {"action": {"type": "string", "enum": ["pause", "resume", "retry", "cancel", "remove"]},
                         "task_ids": {"type": "array", "items": {"type": "string"}},
                         "all": {"type": "boolean"}},
          "required": ["action"]},
         h_control, lambda r: f"{r['action']} × {r['affected']}", read_only=False),
    Tool("tg_index_chat", "建立索引", "Index chat",
         "Scan a chat in the background and store all its file metadata in the local index (incremental: only new "
         "messages since the last scan unless full=true). Afterwards tg_search_files and tg_compare_chats work offline.",
         {"properties": {"account": ACCOUNT, "chat": CHAT, "full": {"type": "boolean", "description": "Rescan from the beginning"}},
          "required": ["chat"]},
         h_index_chat, lambda r: r.get("task_id", ""), read_only=False),
    Tool("tg_index_status", "索引状态", "Index status",
         "List chats in the local index with file counts, total size and whether they are fully indexed.",
         {"properties": {"account": ACCOUNT}}, h_index_status,
         lambda r: L(f"{len(r['chats'])} 个已索引对话", f"{len(r['chats'])} indexed chats")),
    Tool("tg_search_files", "搜索本地文件", "Search local index",
         "Search files across all indexed chats WITHOUT contacting Telegram: by words in name/caption, chats, kinds, "
         "extensions and size; sort by date, size or name.",
         {"properties": {"account": ACCOUNT, "query": {"type": "string", "description": "Words that must all appear"},
                         "chats": {"type": "array", "items": {"type": "string"}, "description": "Limit to these chats"},
                         "types": FILE_FILTERS["types"], "extensions": FILE_FILTERS["extensions"],
                         "min_size_mb": {"type": "number"}, "max_size_mb": {"type": "number"},
                         "sort": {"type": "string", "enum": ["date", "size", "name"], "default": "date"},
                         "limit": {"type": "integer", "default": 50, "maximum": 1000}}},
         h_search_files, lambda r: L(f"{r['matched']} 个匹配 · {r['total_size_human']}", f"{r['matched']} matches · {r['total_size_human']}")),
    Tool("tg_compare_chats", "对比频道", "Compare chats",
         "Compare the indexed files of two chats: what both have, what only one has. by=name (same file name), "
         "name_size (same name and size), stem (name without extension/punctuation) or file (identical Telegram file).",
         {"properties": {"account": ACCOUNT, "chat_a": CHAT, "chat_b": CHAT,
                         "by": {"type": "string", "enum": ["name", "name_size", "stem", "file"], "default": "name_size"},
                         "sample": {"type": "integer", "default": 30}},
          "required": ["chat_a", "chat_b"]},
         h_compare, lambda r: L(f"共有 {r['in_both']['count']} · 仅A {r['only_in_a']['count']} · 仅B {r['only_in_b']['count']}",
                                f"both {r['in_both']['count']} · only A {r['only_in_a']['count']} · only B {r['only_in_b']['count']}")),
    Tool("tg_watch", "订阅频道", "Watch chats",
         "Manage watches that automatically download new matching files from a chat. action=list|add|remove|pause|"
         "resume|check. Watches you add stay disabled until the user approves them in the console.",
         {"properties": {"action": {"type": "string", "enum": ["list", "add", "remove", "pause", "resume", "check"]},
                         "account": ACCOUNT, "chat": CHAT, "watch_id": {"type": "string"},
                         "types": FILE_FILTERS["types"], "name_contains": FILE_FILTERS["name_contains"],
                         "extensions": FILE_FILTERS["extensions"], "min_size_mb": {"type": "number"}, "max_size_mb": {"type": "number"},
                         "interval_min": {"type": "integer", "default": 30, "minimum": 5},
                         "include_recent": {"type": "integer", "description": "On add: also consider the last N messages"},
                         "subdir": {"type": "string"}},
          "required": ["action"]},
         h_watch, lambda r: str(len(r["watches"])) if "watches" in r else r.get("chat_title", r.get("id", "")), read_only=False),
]
TOOL_MAP = {t.name: t for t in TOOLS}


def _brief_args(args: dict) -> str:
    parts = []
    for k, v in args.items():
        if v in (None, "", [], False):
            continue
        s = ", ".join(map(str, v[:3])) + (f" …(+{len(v) - 3})" if len(v) > 3 else "") if isinstance(v, list) else str(v)
        parts.append(f"{k}={s[:60]}")
    return "  ".join(parts)


async def call_tool(name: str, args: dict | None, source: str = "agent", session_id: str = "",
                    transport: str = "api") -> tuple[bool, Any]:
    """Run a tool; returns (ok, result_or_error_message)."""
    tool = TOOL_MAP.get(name)
    if not tool:
        return False, f"Unknown tool: {name}"
    args = {k: v for k, v in (args or {}).items() if v is not None}
    ctx = Ctx(source=source, session_id=session_id or f"{transport}:{source}", transport=transport)
    workflows.touch_session(ctx.session_id, source, transport)

    wf = step = None
    implicit_new = False
    if tool.tracked and transport != "console":
        wf, implicit_new = workflows.current(ctx.session_id, source)
        step, is_poll = workflows.begin_step(wf, name, args)
        if is_poll:   # polls only bump a counter on an existing node; they never overwrite it
            step = None
    token = current_step.set(step)
    t0 = time.time()
    msg: str
    try:
        result = await tool.handler(args, ctx)
        summary = ""
        try:
            summary = tool.summarize(result)
        except Exception:
            pass
        if step is not None:
            workflows.end_step(wf, step, True, result, summary, int((time.time() - t0) * 1000))
        if implicit_new and source not in ("console",) and isinstance(result, dict):
            result = {**result, "_hint": "Tip: call tg_start_workflow(title=...) at the start of each user request "
                                         "so the user can follow your work grouped by request."}
        return True, result
    except FloodWaitError as e:
        msg = L(f"Telegram 限流（FloodWait），需等待 {e.seconds} 秒后再试", f"Telegram rate limit (FloodWait): retry in {e.seconds}s")
    except (AccountError, ValueError, KeyError) as e:
        msg = str(e) if not isinstance(e, KeyError) else f"Missing argument: {e}"
    except RPCError as e:
        msg = f"Telegram error: {e}"
    except Exception as e:
        logging.getLogger("tgagent.tools").exception("tool %s failed", name)
        msg = f"{type(e).__name__}: {e}"
    finally:
        current_step.reset(token)
    if step is not None:
        workflows.end_step(wf, step, False, msg, "", int((time.time() - t0) * 1000))
    else:
        bus.log("error", source, tool.title, msg, tool=name)
    return False, msg
