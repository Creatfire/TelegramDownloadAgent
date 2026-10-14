"""Background tasks: the download queue (concurrency, pause/resume/cancel/retry, resume from
partial files, approval for large AI-initiated batches), exports and local-index scans."""
from __future__ import annotations

import asyncio
import csv
import json
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from telethon.tl import types

from . import index, readers
from .accounts import manager as accounts
from .activity import bus
from .config import EXPORTS_DIR, TASKS_FILE, settings
from .fastdl import SenderPool, parallel_download
from .i18n import L
from .workflow import current_step, workflows

ACTIVE = ("queued", "running")
FINAL = ("done", "failed", "canceled", "skipped")
HUMAN_SOURCES = ("console",)


@dataclass
class Task:
    id: str
    kind: str                      # download / export / index
    account: str
    title: str
    status: str = "queued"         # approval/queued/running/paused/done/failed/canceled/skipped
    source: str = "console"        # who started it (agent name, console, watch:...)
    chat_id: int | None = None
    chat_title: str = ""
    message_id: int | None = None
    file_kind: str = ""
    total: int = 0                 # download: bytes; export/index: messages scanned when finished
    done: int = 0                  # download: bytes; export/index: messages scanned
    path: str = ""
    error: str = ""
    note: str = ""
    params: dict = field(default_factory=dict)
    created: float = field(default_factory=time.time)
    started: float | None = None
    finished: float | None = None
    speed: float = 0.0
    connections: int = 0
    workflow_id: str = ""
    step_id: str = ""
    batch: str = ""                # approval batch id

    def public(self) -> dict:
        d = asdict(self)
        d.pop("params", None)
        d["progress"] = round(self.done / self.total, 4) if self.total else (1.0 if self.status == "done" else 0.0)
        d["eta"] = int((self.total - self.done) / self.speed) if self.speed > 0 and self.total else None
        if self.kind != "download":
            d["params"] = self.params
        return d


_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_name(s: str, max_len: int = 150) -> str:
    s = _BAD.sub("_", str(s)).strip().rstrip(". ")
    if len(s) > max_len:
        stem, dot, ext = s.rpartition(".")
        s = (stem[: max_len - len(ext) - 1] + "." + ext) if dot and len(ext) <= 10 else s[:max_len]
    return s or "_"


class TaskManager:
    def __init__(self) -> None:
        self.tasks: dict[str, Task] = {}
        self._running: dict[str, asyncio.Task] = {}
        self._pools: dict[str, SenderPool] = {}
        self._wake = asyncio.Event()
        self._prev: dict[str, tuple[float, int]] = {}
        self._dirty = False
        self._load()

    # ---------------------------------------------------------------- persistence
    def _load(self) -> None:
        if not TASKS_FILE.exists():
            return
        try:
            known = Task.__dataclass_fields__
            for raw in json.loads(TASKS_FILE.read_text("utf-8")):
                t = Task(**{k: v for k, v in raw.items() if k in known})
                if t.status == "running":
                    if t.kind == "download":
                        t.status = "queued"
                    else:
                        t.status, t.error = "failed", L("服务重启时中断", "Interrupted by a restart")
                t.speed = 0
                self.tasks[t.id] = t
        except Exception:
            pass

    def save(self) -> None:
        items = sorted(self.tasks.values(), key=lambda t: t.created)
        finals = [t for t in items if t.status in FINAL]
        drop = {t.id for t in finals[:-3000]} if len(finals) > 3000 else set()
        for i in drop:
            self.tasks.pop(i, None)
        TASKS_FILE.write_text(json.dumps([asdict(t) for t in items if t.id not in drop], ensure_ascii=False), "utf-8")
        self._dirty = False

    def _changed(self, t: Task) -> None:
        self._dirty = True
        bus.emit("task", t.public())

    def _new(self, **kw) -> Task:
        step = current_step.get()
        t = Task(id=uuid.uuid4().hex[:10], **kw)
        if step is not None and step.id:
            t.workflow_id, t.step_id = step.workflow_id, step.id
        self.tasks[t.id] = t
        return t

    # ---------------------------------------------------------------- queries
    def list(self, status: str | None = None, ids: list[str] | None = None, kind: str | None = None,
             limit: int = 50) -> list[dict]:
        items = sorted(self.tasks.values(), key=lambda t: t.created, reverse=True)
        if ids:
            items = [t for t in items if t.id in ids]
        if kind:
            items = [t for t in items if t.kind == kind]
        if status and status != "all":
            want = ACTIVE if status == "active" else (status,)
            items = [t for t in items if t.status in want]
        return [t.public() for t in items[: max(1, min(int(limit or 50), 1000))]]

    def stats(self) -> dict:
        s: dict[str, Any] = {"approval": 0, "queued": 0, "running": 0, "paused": 0, "done": 0, "failed": 0}
        speed, remaining = 0.0, 0
        for t in self.tasks.values():
            if t.status in s:
                s[t.status] += 1
            if t.kind == "download" and t.status == "running":
                speed += t.speed
            if t.kind == "download" and t.status in ("queued", "running", "paused"):
                remaining += max(0, t.total - t.done)
        s["speed"] = speed
        s["remaining_bytes"] = remaining
        return s

    def approvals(self) -> list[dict]:
        groups: dict[str, dict] = {}
        for t in sorted(self.tasks.values(), key=lambda t: t.created):
            if t.status != "approval":
                continue
            g = groups.setdefault(t.batch, {"batch": t.batch, "source": t.source, "chat_title": t.chat_title,
                                            "workflow_id": t.workflow_id, "step_id": t.step_id,
                                            "count": 0, "size": 0, "created": t.created, "sample": []})
            g["count"] += 1
            g["size"] += t.total
            if len(g["sample"]) < 5:
                g["sample"].append(t.title)
        return list(groups.values())

    # ---------------------------------------------------------------- downloads
    async def enqueue_downloads(self, account: str | None, source: str, links: list[str] | None = None,
                                chat: str | None = None, message_ids: list[int] | None = None,
                                limit: int = 50, oldest_first: bool = False, subdir: str = "",
                                include_album: bool = False, skip_approval: bool = False,
                                min_id: int = 0, **filters) -> dict:
        acc, client = await accounts.client(account)
        pairs: list[tuple[Any, Any]] = []

        for link in links or []:
            cr = readers.parse_ref(link)
            if not cr.msg_id:
                raise ValueError(L(f"链接缺少消息 ID: {link}", f"Link has no message id: {link}"))
            entity = await readers._entity(client, cr.chat)
            msg = await client.get_messages(entity, ids=cr.msg_id)
            if msg:
                pairs.append((entity, msg))
        if chat and message_ids:
            entity = await readers.get_entity(client, chat)
            for msg in await client.get_messages(entity, ids=[int(i) for i in message_ids]):
                if msg:
                    pairs.append((entity, msg))
        elif chat and not links:
            entity = await readers.get_entity(client, chat)
            flt = readers.FileFilter(**filters)
            limit = max(1, min(int(limit or 50), 5000))
            async for msg, fi in readers.iter_files(client, entity, flt, oldest_first=oldest_first, min_id=min_id):
                if fi:
                    pairs.append((entity, msg))
                    if len(pairs) >= limit:
                        break

        if include_album:
            extra = []
            for entity, msg in pairs:
                if msg.grouped_id:
                    around = await client.get_messages(entity, ids=list(range(msg.id - 10, msg.id + 11)))
                    extra += [(entity, m) for m in around if m and m.grouped_id == msg.grouped_id]
            pairs += extra

        candidates, skipped, seen = [], [], set()
        for entity, msg in pairs:
            chat_id = readers.utils.get_peer_id(entity)
            if (chat_id, msg.id) in seen:
                continue
            seen.add((chat_id, msg.id))
            fi = readers.file_info(msg)
            if not fi:
                skipped.append({"message_id": msg.id, "reason": L("没有可下载的文件", "no downloadable file")})
                continue
            dup = next((t for t in self.tasks.values() if t.kind == "download" and t.account == acc.id
                        and t.chat_id == chat_id and t.message_id == msg.id
                        and t.status in ("approval", "queued", "running", "paused")), None)
            if dup:
                skipped.append({"message_id": msg.id, "reason": L(f"已在队列中 ({dup.id})", f"already queued ({dup.id})")})
                continue
            candidates.append((entity, msg, chat_id, fi))

        total = sum(fi["size"] for *_, fi in candidates)
        need_approval = (not skip_approval and source not in HUMAN_SOURCES and candidates
                         and self._over_limit(len(candidates), total))
        batch = uuid.uuid4().hex[:8] if need_approval else ""
        created = []
        for entity, msg, chat_id, fi in candidates:
            t = self._new(kind="download", account=acc.id, title=fi["name"], source=source,
                          status="approval" if need_approval else "queued", batch=batch,
                          chat_id=chat_id, chat_title=readers.chat_title(entity), message_id=msg.id,
                          file_kind=fi["kind"], total=fi["size"],
                          params={"subdir": subdir, "date": readers.iso(msg.date)})
            t.path = str(self._dest_path(t, fi["name"]))
            created.append(t)
            self._changed(t)
        workflows.attach_tasks(current_step.get(), [t.id for t in created])
        self.save()
        self._wake.set()
        if created:
            if need_approval:
                bus.log("warn", source, L("下载等待批准", "Download awaits approval"),
                        f"{created[0].chat_title} · {len(created)} · {readers.human_size(total)}", batch=batch)
            else:
                bus.log("info", source, L(f"加入下载队列：{len(created)} 个文件", f"Queued {len(created)} file(s)"),
                        f"{created[0].chat_title} · {readers.human_size(total)}")
        out = {
            "queued": 0 if need_approval else len(created), "total_size": total,
            "total_size_human": readers.human_size(total), "download_dir": settings.get("download_dir"),
            "tasks": [{"task_id": t.id, "name": t.title, "size": t.total, "path": t.path} for t in created],
            "skipped": skipped,
        }
        if need_approval:
            out.update({
                "requires_approval": True, "approval_batch": batch, "awaiting_approval": len(created),
                "hint": L("超过自动下载限额，已等待用户在 Web 控制台批准。告诉用户去控制台批准，之后可用 tg_tasks 查看状态。",
                          "Over the auto-download limit: waiting for the user to approve it in the web console. "
                          "Tell the user, then check progress with tg_tasks."),
            })
        else:
            out["hint"] = L("用 tg_tasks 查看进度；用户可在 Web 控制台实时查看",
                            "Use tg_tasks to follow progress; the user sees it live in the web console")
        return out

    @staticmethod
    def _over_limit(count: int, size: int) -> bool:
        gb = float(settings.get("approval_size_gb") or 0)
        n = int(settings.get("approval_files") or 0)
        return (gb > 0 and size > gb * 1024 ** 3) or (n > 0 and count > n)

    def approve(self, batch: str, ok: bool, source: str = "console") -> dict:
        items = [t for t in self.tasks.values() if t.batch == batch and t.status == "approval"]
        for t in items:
            t.status = "queued" if ok else "canceled"
            if not ok:
                t.finished = time.time()
            self._changed(t)
        self.save()
        self._wake.set()
        if items:
            bus.log("success" if ok else "warn", source,
                    L("已批准下载" if ok else "已拒绝下载", "Download approved" if ok else "Download rejected"),
                    f"{items[0].chat_title} · {len(items)}", batch=batch)
        return {"batch": batch, "approved": ok, "affected": len(items)}

    def _dest_path(self, t: Task, name: str) -> Path:
        tpl = settings.get("name_template") or "{chat}/{msg_id}_{name}"
        date = (t.params.get("date") or "")[:10]
        rel = tpl.format(chat=t.chat_title, chat_id=t.chat_id, msg_id=t.message_id, name=name, date=date)
        parts = [safe_name(p) for p in rel.replace("\\", "/").split("/") if p.strip()]
        root = Path(settings.get("download_dir"))
        if t.params.get("subdir"):
            root = root / safe_name(t.params["subdir"])
        return root.joinpath(*parts)

    # ---------------------------------------------------------------- control
    async def control(self, action: str, ids: list[str] | None = None, all_: bool = False, source: str = "console") -> dict:
        targets = list(self.tasks.values()) if all_ else [self.tasks[i] for i in (ids or []) if i in self.tasks]
        changed = []
        for t in targets:
            if action == "pause" and t.status in ACTIVE and t.kind == "download":
                await self._stop(t, "paused")
            elif action == "resume" and t.status == "paused":
                t.status = "queued"
            elif action == "retry" and t.status in ("failed", "canceled") and t.kind == "download":
                t.status, t.error = "queued", ""
            elif action == "cancel" and t.status in ("approval", "queued", "running", "paused"):
                await self._stop(t, "canceled")
                self._cleanup_part(t)
            elif action == "remove" and t.status in FINAL:
                self.tasks.pop(t.id, None)
            else:
                continue
            changed.append(t.id)
            self._changed(t)
        self.save()
        self._wake.set()
        if changed:
            names = {"pause": L("暂停", "Paused"), "resume": L("继续", "Resumed"), "retry": L("重试", "Retried"),
                     "cancel": L("取消", "Canceled"), "remove": L("移除", "Removed")}
            bus.log("info", source, f"{names.get(action, action)} × {len(changed)}")
        return {"action": action, "affected": len(changed), "task_ids": changed}

    async def _stop(self, t: Task, status: str) -> None:
        t.status = status
        job = self._running.pop(t.id, None)
        if job:
            job.cancel()
            try:
                await job
            except BaseException:
                pass
        t.status, t.speed = status, 0
        if status in FINAL:
            t.finished = time.time()

    def _cleanup_part(self, t: Task) -> None:
        if t.kind != "download" or not t.path:
            return
        p = Path(t.path + ".part")
        for f in (p, p.with_name(p.name + ".json")):
            try:
                f.unlink()
            except FileNotFoundError:
                pass

    # ---------------------------------------------------------------- scheduling
    async def run_forever(self) -> None:
        asyncio.create_task(self._ticker())
        while True:
            self._schedule()
            self._wake.clear()
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=2)
            except asyncio.TimeoutError:
                pass

    def _schedule(self) -> None:
        limit = max(1, int(settings.get("max_concurrent_files") or 2))
        running = sum(1 for i in self._running if self.tasks.get(i) and self.tasks[i].kind == "download")
        queued = sorted((t for t in self.tasks.values() if t.kind == "download" and t.status == "queued"),
                        key=lambda t: t.created)
        for t in queued:
            if running >= limit:
                break
            acc = accounts.accounts.get(t.account)
            if not acc or acc.status != "ready":
                continue
            t.status, t.started, t.error = "running", time.time(), ""
            self._running[t.id] = asyncio.create_task(self._run_download(t))
            running += 1
            self._changed(t)

    async def _ticker(self) -> None:
        while True:
            await asyncio.sleep(1)
            now = time.time()
            for tid in list(self._running):
                t = self.tasks.get(tid)
                if not t:
                    continue
                if t.kind == "download":
                    pt, pd = self._prev.get(tid, (now - 1, t.done))
                    inst = max(0.0, (t.done - pd) / max(0.001, now - pt))
                    t.speed = inst if t.speed == 0 else t.speed * 0.6 + inst * 0.4
                    self._prev[tid] = (now, t.done)
                bus.emit("task", t.public())
            bus.emit("stats", self.stats())
            if self._dirty:
                self.save()
            for acc_id, pool in list(self._pools.items()):
                busy = any(self.tasks[i].account == acc_id for i in self._running if i in self.tasks)
                if not busy and now - pool.last_used > 120 and pool.total:
                    await pool.close_all()

    def _pool(self, acc_id: str, client) -> SenderPool:
        pool = self._pools.get(acc_id)
        if not pool or pool.client is not client:
            pool = self._pools[acc_id] = SenderPool(client)
        return pool

    async def _run_download(self, t: Task) -> None:
        path = Path(t.path)
        part = Path(t.path + ".part")
        try:
            acc, client = await accounts.client(t.account)
            entity = await readers._entity(client, t.chat_id)
            msg = await client.get_messages(entity, ids=t.message_id)
            if not msg or not msg.media:
                raise ValueError(L("消息已删除或不再包含文件", "Message deleted or no longer has a file"))
            if path.exists() and path.stat().st_size == t.total:
                t.status, t.done, t.note = "skipped", t.total, L("文件已存在", "already exists")
                return
            path.parent.mkdir(parents=True, exist_ok=True)
            t.done = 0
            self._prev.pop(t.id, None)

            def progress(n: int) -> None:
                t.done += n

            media = msg.document or msg.photo
            if isinstance(media, types.Document):
                conns = max(1, int(settings.get("connections_per_file") or 4))
                part_size = int(settings.get("part_size_kb") or 512) * 1024
                part_size = min(1024 * 1024, max(4096, part_size - part_size % 4096))
                if 1024 * 1024 % part_size:
                    part_size = 512 * 1024
                t.connections = conns

                async def refresh():
                    m = await client.get_messages(entity, ids=t.message_id)
                    return m.document

                def on_event(level: str, text: str) -> None:
                    bus.log(level, "download", f"{t.title}: {text}", task_id=t.id)

                await parallel_download(self._pool(acc.id, client), media, part, conns, part_size,
                                        progress, refresh, on_event)
            else:
                t.connections = 1
                last = [0]

                def cb(cur, total):
                    progress(cur - last[0])
                    last[0] = cur
                await client.download_media(msg, file=str(part), progress_callback=cb)
                t.total = part.stat().st_size
                t.done = t.total
            if path.exists():  # same name, different size: keep both
                stem, suf, n = path.stem, path.suffix, 1
                while path.exists():
                    path = path.with_name(f"{stem} ({n}){suf}")
                    n += 1
                t.path = str(path)
            part.replace(path)
            t.status = "done"
            bus.log("success", "download", L(f"下载完成：{t.title}", f"Downloaded: {t.title}"),
                    f"{readers.human_size(t.total)} · {int(time.time() - (t.started or time.time()))}s", task_id=t.id)
        except asyncio.CancelledError:
            if t.status == "running":
                t.status = "paused"
            raise
        except Exception as e:
            t.status, t.error = "failed", f"{type(e).__name__}: {e}"
            bus.log("error", "download", L(f"下载失败：{t.title}", f"Download failed: {t.title}"), t.error, task_id=t.id)
        finally:
            t.speed = 0
            if t.status in FINAL:
                t.finished = time.time()
            self._running.pop(t.id, None)
            self._changed(t)
            self._wake.set()

    # ---------------------------------------------------------------- background scans
    def _start_job(self, t: Task, coro) -> None:
        self._changed(t)
        self._running[t.id] = asyncio.create_task(coro)
        workflows.attach_tasks(current_step.get(), [t.id])

    async def start_export(self, account: str | None, source: str, chat: str, what: str = "files",
                           fmt: str = "csv", limit: int | None = None, oldest_first: bool = False,
                           **filters) -> dict:
        acc, client = await accounts.client(account)
        entity = await readers.get_entity(client, chat)
        what = "messages" if what == "messages" else "files"
        fmt = fmt if fmt in ("csv", "json", "jsonl", "md") else "csv"
        if fmt == "md" and what == "files":
            fmt = "csv"
        title = readers.chat_title(entity)
        out = EXPORTS_DIR / f"{safe_name(title, 60)}_{what}_{time.strftime('%Y%m%d_%H%M%S')}.{fmt}"
        label = L("文件清单", "file list") if what == "files" else L("消息记录", "messages")
        t = self._new(kind="export", account=acc.id, title=L(f"导出 {title} 的{label}", f"Export {label} of {title}"),
                      source=source, chat_id=readers.utils.get_peer_id(entity), chat_title=title, path=str(out),
                      status="running", started=time.time(),
                      params={"what": what, "format": fmt, "limit": limit, "oldest_first": oldest_first, **filters})
        self._start_job(t, self._run_export(t, client, entity, filters))
        return {"task_id": t.id, "status": "running", "output_path": str(out),
                "hint": L("导出在后台进行，用 tg_tasks(task_ids=[...]) 查看是否完成，完成后读取 output_path",
                          "Runs in the background; check tg_tasks(task_ids=[...]) and read output_path when done")}

    async def start_index(self, account: str | None, source: str, chat: str, full: bool = False) -> dict:
        acc, client = await accounts.client(account)
        entity = await readers.get_entity(client, chat)
        chat_id = readers.utils.get_peer_id(entity)
        title = readers.chat_title(entity)
        busy = next((t for t in self.tasks.values() if t.kind == "index" and t.chat_id == chat_id
                     and t.status == "running"), None)
        if busy:
            return {"task_id": busy.id, "status": "running", "hint": L("该对话已在建立索引", "Already indexing this chat")}
        state = index.chat_state(acc.id, chat_id) or {}
        min_id = 0 if full else int(state.get("max_scanned_id") or 0)
        t = self._new(kind="index", account=acc.id, title=L(f"索引 {title}", f"Index {title}"), source=source,
                      chat_id=chat_id, chat_title=title, status="running", started=time.time(),
                      params={"full": full, "from_message_id": min_id})
        self._start_job(t, self._run_index(t, client, entity, min_id))
        return {"task_id": t.id, "status": "running", "incremental_from": min_id,
                "hint": L("索引在后台进行。完成后可用 tg_search_files / tg_compare_chats 离线查询。",
                          "Indexing in the background. When done, query offline with tg_search_files / tg_compare_chats.")}

    async def _run_index(self, t: Task, client, entity, min_id: int) -> None:
        files = 0
        max_id = min_id
        try:
            async for msg, fi in readers.iter_files(client, entity, readers.FileFilter(), oldest_first=True, min_id=min_id):
                t.done += 1
                max_id = max(max_id, msg.id)
                if fi:
                    files += 1
            index.mark_full_scan(t.account, t.chat_id, max_id)
            st = index.chat_state(t.account, t.chat_id) or {}
            t.total, t.status = t.done, "done"
            t.note = L(f"新增 {files} 个文件，共 {st.get('files', 0)} 个 · {readers.human_size(st.get('total_size', 0))}",
                       f"{files} new, {st.get('files', 0)} total · {readers.human_size(st.get('total_size', 0))}")
            bus.log("success", "index", L(f"索引完成：{t.chat_title}", f"Indexed: {t.chat_title}"), t.note, task_id=t.id)
        except asyncio.CancelledError:
            t.status = "canceled"
            raise
        except Exception as e:
            index.flush({(t.account, t.chat_id): max_id})
            t.status, t.error = "failed", f"{type(e).__name__}: {e}"
            bus.log("error", "index", L(f"索引失败：{t.chat_title}", f"Index failed: {t.chat_title}"), t.error, task_id=t.id)
        finally:
            t.finished = time.time()
            self._running.pop(t.id, None)
            self._changed(t)

    async def _run_export(self, t: Task, client, entity, filters: dict) -> None:
        p = t.params
        limit = int(p["limit"]) if p.get("limit") else None
        rows: list[dict] = []
        total_size = 0
        try:
            if p["what"] == "files":
                flt = readers.FileFilter(**filters)
                async for msg, fi in readers.iter_files(client, entity, flt, oldest_first=p["oldest_first"]):
                    t.done += 1
                    if fi:
                        rows.append(readers.file_row(msg, entity, fi))
                        total_size += fi["size"]
                        if limit and len(rows) >= limit:
                            break
            else:
                since, until = readers.parse_date(filters.get("since")), readers.parse_date(filters.get("until"))
                kw: dict[str, Any] = dict(reverse=p["oldest_first"], wait_time=settings.get("read_wait_time"))
                if p["oldest_first"] and since:
                    kw["offset_date"] = since
                elif not p["oldest_first"] and until:
                    kw["offset_date"] = until
                async for msg in client.iter_messages(entity, **kw):
                    t.done += 1
                    if since and not p["oldest_first"] and msg.date < since:
                        break
                    if until and p["oldest_first"] and msg.date > until:
                        break
                    if isinstance(msg, types.MessageService):
                        continue
                    rows.append(readers.message_dict(msg, entity, text_max=None))
                    if limit and len(rows) >= limit:
                        break
            self._write_export(Path(t.path), rows, p["format"], p["what"], t.chat_title)
            t.total = t.done
            t.status = "done"
            t.note = L(f"{len(rows)} 条", f"{len(rows)} rows") + (
                f" · {readers.human_size(total_size)}" if p["what"] == "files" else "")
            bus.log("success", "export", L(f"导出完成：{t.chat_title}", f"Exported: {t.chat_title}"), t.note, task_id=t.id)
        except asyncio.CancelledError:
            t.status = "canceled"
            raise
        except Exception as e:
            t.status, t.error = "failed", f"{type(e).__name__}: {e}"
            bus.log("error", "export", L(f"导出失败：{t.chat_title}", f"Export failed: {t.chat_title}"), t.error, task_id=t.id)
        finally:
            t.finished = time.time()
            self._running.pop(t.id, None)
            self._changed(t)

    @staticmethod
    def _write_export(path: Path, rows: list[dict], fmt: str, what: str, title: str) -> None:
        if fmt == "json":
            path.write_text(json.dumps(rows, ensure_ascii=False, indent=1), "utf-8")
        elif fmt == "jsonl":
            path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), "utf-8")
        elif fmt == "md":
            lines = [f"# {title}\n"]
            for r in rows:
                head = f"**#{r['id']}** · {r['date']}"
                if r.get("sender"):
                    head += f" · {r['sender'].get('name')}"
                lines.append(head)
                if r.get("file"):
                    lines.append(f"📎 {r['file']['name']} ({readers.human_size(r['file']['size'])})")
                if r.get("text"):
                    lines.append(r["text"])
                lines.append("")
            path.write_text("\n".join(lines), "utf-8")
        else:
            if what == "files":
                cols = ["message_id", "date", "kind", "name", "size", "ext", "mime", "duration", "resolution", "link", "caption"]
            else:
                cols = ["id", "date", "sender", "text", "file_name", "file_size", "views", "link"]
                rows = [{**r, "sender": (r.get("sender") or {}).get("name", ""),
                         "file_name": (r.get("file") or {}).get("name", ""),
                         "file_size": (r.get("file") or {}).get("size", "")} for r in rows]
            with path.open("w", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
                w.writeheader()
                w.writerows(rows)

    async def shutdown(self) -> None:
        interrupted = [tid for tid in self._running if self.tasks.get(tid) and self.tasks[tid].kind == "download"]
        jobs = list(self._running.values())
        for job in jobs:
            job.cancel()
        await asyncio.gather(*jobs, return_exceptions=True)
        for tid in interrupted:  # resume automatically on next start
            self.tasks[tid].status = "queued"
        self.save()
        for pool in self._pools.values():
            await pool.close_all()


tasks: TaskManager | None = None


def get_tasks() -> TaskManager:
    global tasks
    if tasks is None:
        tasks = TaskManager()
    return tasks
