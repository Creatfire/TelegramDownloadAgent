"""Parallel chunked downloader (same idea as tdl / FastTelethon).

Telethon downloads parts sequentially over one connection. Here a file is fetched over several independent
MTProto connections at once, parts are written into a pre-allocated .part file, and finished parts are
recorded in .part.json so downloads can resume.
"""
from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
import time
from pathlib import Path
from typing import Awaitable, Callable

from telethon import TelegramClient, utils
from telethon.errors import FloodWaitError, FileReferenceExpiredError, RPCError
from telethon.network import MTProtoSender
from telethon.tl import functions, types
from telethon.tl.alltlobjects import LAYER

log = logging.getLogger("tgagent.fastdl")

PART_TIMEOUT = 60
MAX_PART_RETRIES = 6
MAX_ROUNDS = 4


class SenderPool:
    """Reusable extra MTProto connections per DC; one pool per account."""

    def __init__(self, client: TelegramClient):
        self.client = client
        self.idle: dict[int, list[MTProtoSender]] = {}
        self.total = 0
        self._lock = asyncio.Lock()
        self.last_used = time.time()

    async def acquire(self, dc_id: int) -> MTProtoSender:
        self.last_used = time.time()
        bucket = self.idle.setdefault(dc_id, [])
        while bucket:
            s = bucket.pop()
            if s.is_connected():
                return s
            self.total -= 1
        async with self._lock:  # create one at a time to avoid exporting many authorizations at once
            s = await self._create(dc_id)
            self.total += 1
            return s

    def release(self, dc_id: int, sender: MTProtoSender) -> None:
        self.last_used = time.time()
        self.idle.setdefault(dc_id, []).append(sender)

    async def discard(self, sender: MTProtoSender) -> None:
        self.total -= 1
        try:
            await sender.disconnect()
        except Exception:
            pass

    async def close_all(self) -> None:
        for bucket in self.idle.values():
            for s in bucket:
                try:
                    await s.disconnect()
                except Exception:
                    pass
        self.idle.clear()
        self.total = 0

    async def _create(self, dc_id: int) -> MTProtoSender:
        c = self.client
        dc = await c._get_dc(dc_id)
        same_dc = dc_id == c.session.dc_id
        sender = MTProtoSender(c.session.auth_key if same_dc else None, loggers=c._log)
        await sender.connect(c._connection(dc.ip_address, dc.port, dc.id, loggers=c._log,
                                           proxy=c._proxy, local_addr=c._local_addr))
        init = copy.copy(c._init_request)
        if same_dc:
            init.query = functions.help.GetConfigRequest()
        else:
            auth = await c(functions.auth.ExportAuthorizationRequest(dc_id))
            init.query = functions.auth.ImportAuthorizationRequest(id=auth.id, bytes=auth.bytes)
        await sender.send(functions.InvokeWithLayerRequest(LAYER, init))
        return sender


class DownloadAborted(Exception):
    pass


async def parallel_download(
    pool: SenderPool,
    media,                      # Document or Photo
    part_path: Path,
    connections: int,
    part_size: int,
    on_progress: Callable[[int], None],
    refresh_media: Callable[[], Awaitable[object]],
    on_event: Callable[[str, str], None] = lambda level, text: None,
) -> None:
    """Download media into part_path (the caller renames it). Cancellable; progress is kept for resuming."""
    info = utils._get_file_info(media)
    dc_id, location, size = info.dc_id, info.location, info.size
    if not size:
        raise ValueError("Unknown file size")
    n_parts = (size + part_size - 1) // part_size
    meta_path = part_path.with_name(part_path.name + ".json")
    file_id = getattr(media, "id", 0)

    done: set[int] = set()
    if part_path.exists() and meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text("utf-8"))
            if meta.get("id") == file_id and meta.get("size") == size and meta.get("part_size") == part_size:
                done = set(meta.get("done", []))
        except Exception:
            done = set()
    if not done and part_path.exists():
        part_path.unlink()

    already = sum(min(part_size, size - i * part_size) for i in done)
    on_progress(already)

    def finish() -> None:
        try:
            meta_path.unlink()
        except FileNotFoundError:
            pass

    # Resume data says every part is already there (e.g. finishing failed last time): finish without connecting
    if len(done) == n_parts and part_path.exists() and part_path.stat().st_size == size:
        finish()
        return

    mode = "r+b" if part_path.exists() else "wb"
    f = open(part_path, mode)
    if mode == "wb":
        f.truncate(size)

    queue: asyncio.Queue[int] = asyncio.Queue()
    for i in range(n_parts):
        if i not in done:
            queue.put_nowait(i)

    loc_lock = asyncio.Lock()
    state = {"location": location, "last_save": time.time()}

    def save_meta(force: bool = False) -> None:
        if force or time.time() - state["last_save"] > 2:
            meta_path.write_text(json.dumps({"id": file_id, "size": size, "part_size": part_size,
                                             "done": sorted(done)}), "utf-8")
            state["last_save"] = time.time()

    async def refresh_location(old) -> None:
        async with loc_lock:
            if state["location"] is not old:
                return
            new_media = await refresh_media()
            state["location"] = utils._get_file_info(new_media).location
            on_event("info", "File reference expired; refreshed")

    async def worker() -> None:
        sender: MTProtoSender | None = None
        try:
            while True:
                try:
                    idx = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                offset = idx * part_size
                last_err: BaseException | None = None
                data = None
                for attempt in range(MAX_PART_RETRIES):
                    loc = state["location"]
                    try:
                        if sender is None:
                            sender = await asyncio.wait_for(pool.acquire(dc_id), timeout=PART_TIMEOUT)
                        res = await asyncio.wait_for(
                            sender.send(functions.upload.GetFileRequest(loc, offset=offset, limit=part_size)),
                            timeout=PART_TIMEOUT)
                        if not isinstance(res, types.upload.File):
                            raise RuntimeError("CDN redirect is not supported")
                        data = res.bytes
                        break
                    except FloodWaitError as e:
                        on_event("warn", f"FloodWait: waiting {e.seconds}s")
                        await asyncio.sleep(e.seconds + 1)
                    except FileReferenceExpiredError:
                        await refresh_location(loc)
                    except RPCError:
                        queue.put_nowait(idx)
                        raise  # other Telegram errors (e.g. file gone) won't succeed on retry
                    except Exception as e:
                        # Network errors: proxies dropping connections raise IncompleteReadError (an EOFError), timeouts, resets…
                        last_err = e
                        log.warning("part %s attempt %s failed: %r", idx, attempt + 1, e)
                        if sender is not None:
                            await pool.discard(sender)
                            sender = None
                        await asyncio.sleep(min(2 ** attempt, 20))
                if data is None:
                    queue.put_nowait(idx)  # hand it back to another connection or the next round
                    raise ConnectionError(f"Part {idx} failed after {MAX_PART_RETRIES} attempts: {last_err!r}")
                f.seek(offset)
                f.write(data)
                done.add(idx)
                on_progress(len(data))
                save_meta()
        finally:
            if sender is not None and sender.is_connected():
                pool.release(dc_id, sender)

    try:
        # One failing connection doesn't stop the others; leftover parts get new connections next round.
        # Only a round without any progress counts as failure.
        last_error: BaseException | None = None
        for _ in range(MAX_ROUNDS):
            if queue.empty():
                break
            before = len(done)
            workers = [asyncio.create_task(worker()) for _ in range(max(1, min(connections, queue.qsize())))]
            try:
                results = await asyncio.gather(*workers, return_exceptions=True)
            except BaseException:
                for w in workers:
                    w.cancel()
                await asyncio.gather(*workers, return_exceptions=True)
                raise
            errors = [r for r in results if isinstance(r, BaseException)]
            if errors:
                last_error = errors[0]
                if isinstance(last_error, RPCError):
                    raise last_error
                if len(done) == before:
                    break
                on_event("warn", f"{len(errors)} connection(s) dropped; continuing with new ones")
        # Success is decided by the parts actually written, not by earlier worker errors
        if len(done) != n_parts:
            raise last_error or DownloadAborted("Not all parts finished")
    except BaseException:
        f.flush()
        f.close()
        save_meta(force=True)
        raise
    f.close()
    finish()
