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
RAISE_AFTER = 20        # seconds without FloodWait before the limiter adds a slot back


class AdaptiveLimiter:
    """Caps in-flight GetFile requests per account and adapts to Telegram's rate limit (AIMD):
    a FloodWait halves the cap and pauses every request until it expires; quiet periods add slots back."""

    def __init__(self, max_slots: int = 8):
        self.max = max(1, max_slots)
        self.limit = self.max
        self.active = 0
        self.flood_until = 0.0
        self.last_change = time.time()
        self.floods = 0
        self._changed = asyncio.Event()

    def set_max(self, n: int) -> None:
        n = max(1, int(n))
        if n != self.max:
            self.max = n
            self.limit = min(self.limit, n) if self.limit else n
            self._changed.set()

    async def acquire(self) -> None:
        while True:
            wait = self.flood_until - time.time()
            if wait > 0:
                await asyncio.sleep(wait)
                continue
            if self.active < self.limit:
                self.active += 1
                return
            self._changed.clear()
            try:
                await asyncio.wait_for(self._changed.wait(), timeout=1)
            except asyncio.TimeoutError:
                pass

    def release(self) -> None:
        self.active = max(0, self.active - 1)
        self._changed.set()

    def on_flood(self, seconds: int) -> None:
        now = time.time()
        self.floods += 1
        self.flood_until = max(self.flood_until, now + seconds + 1)
        if now - self.last_change > 2:          # several workers report the same flood at once: halve once
            self.limit = max(1, self.limit // 2)
            self.last_change = now

    def on_success(self) -> None:
        now = time.time()
        if self.limit < self.max and now - max(self.last_change, self.flood_until) > RAISE_AFTER:
            self.limit += 1
            self.last_change = now
            self._changed.set()


class RateLimiter:
    """Global token bucket shared by all downloads (bytes per second; 0 = unlimited)."""

    def __init__(self) -> None:
        self.rate = 0
        self.tokens = 0.0
        self.ts = time.time()

    async def consume(self, n: int) -> None:
        if self.rate <= 0:
            return
        now = time.time()
        self.tokens = min(self.rate, self.tokens + (now - self.ts) * self.rate)
        self.ts = now
        self.tokens -= n
        if self.tokens < 0:
            await asyncio.sleep(-self.tokens / self.rate)


RATE = RateLimiter()


class SenderPool:
    """Reusable extra MTProto connections per DC; one pool per account."""

    def __init__(self, client: TelegramClient):
        self.client = client
        self.idle: dict[int, list[MTProtoSender]] = {}
        self.total = 0
        self._lock = asyncio.Lock()
        self.last_used = time.time()
        self.limiter = AdaptiveLimiter()

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
    on_state: Callable[[str | None, float | None], None] = lambda reason, until: None,
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

    limiter: AdaptiveLimiter | None = getattr(pool, "limiter", None)

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
                failures = 0          # only network failures count; FloodWait waits never fail a part
                while failures < MAX_PART_RETRIES:
                    loc = state["location"]
                    if limiter:
                        await limiter.acquire()
                    try:
                        if sender is None:
                            sender = await asyncio.wait_for(pool.acquire(dc_id), timeout=PART_TIMEOUT)
                        res = await asyncio.wait_for(
                            sender.send(functions.upload.GetFileRequest(loc, offset=offset, limit=part_size)),
                            timeout=PART_TIMEOUT)
                        if not isinstance(res, types.upload.File):
                            raise RuntimeError("CDN redirect is not supported")
                        data = res.bytes
                        if limiter:
                            limiter.on_success()
                        on_state(None, None)
                        break
                    except FloodWaitError as e:
                        if limiter:
                            limiter.on_flood(e.seconds)
                            on_state("flood", limiter.flood_until)
                        else:
                            on_state("flood", time.time() + e.seconds)
                            await asyncio.sleep(e.seconds + 1)
                    except FileReferenceExpiredError:
                        await refresh_location(loc)
                    except RPCError:
                        queue.put_nowait(idx)
                        raise  # other Telegram errors (e.g. file gone) won't succeed on retry
                    except Exception as e:
                        # Network errors: proxies dropping connections raise IncompleteReadError (an EOFError), timeouts, resets…
                        last_err = e
                        failures += 1
                        log.warning("part %s attempt %s failed: %r", idx, failures, e)
                        on_state("reconnecting", None)
                        if sender is not None:
                            await pool.discard(sender)
                            sender = None
                        await asyncio.sleep(min(2 ** failures, 20))
                    finally:
                        if limiter:
                            limiter.release()
                if data is None:
                    queue.put_nowait(idx)  # hand it back to another connection or the next round
                    raise ConnectionError(f"Part {idx} failed after {MAX_PART_RETRIES} attempts: {last_err!r}")
                await RATE.consume(len(data))
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
