"""Offline tests for v1.1: split archives, adaptive limiter, download window, speed display, reports."""
from __future__ import annotations

import asyncio
import time

import pytest

from tgagent import readers, tasks
from tgagent.config import settings
from tgagent.fastdl import AdaptiveLimiter, RateLimiter


@pytest.mark.parametrize("name, expect", [
    ("game.7z.001", ("game.7z", 1)),
    ("GAME.7Z.012", ("GAME.7Z", 12)),
    ("movie.part3.rar", ("movie.rar", 3)),
    ("disk.z02", ("disk.zip", 2)),
    ("backup.001", ("backup", 1)),
    ("clip.mp4", None),
    ("v2.1.zip", None),
])
def test_split_info(name, expect):
    r = readers.split_info(name)
    assert (r and (r["set"], r["part"])) == (expect or None) or (r is None and expect is None)


def test_archive_sets_missing():
    rows = [{"name": f"a.7z.00{i}", "size": 10, "message_id": i, "archive": readers.split_info(f"a.7z.00{i}")}
            for i in (1, 2, 4)]
    sets = readers.archive_sets(rows)
    assert len(sets) == 1 and sets[0]["parts"] == [1, 2, 4] and sets[0]["missing"] == [3] and sets[0]["size"] == 30


def test_human_size_small_is_zero_kb():
    assert readers.human_size(0) == "0 KB"
    assert readers.human_size(4.8e-21) == "0 KB"
    assert readers.human_size(1023) == "0 KB"
    assert readers.human_size(2048) == "2.00 KB"


def test_adaptive_limiter():
    async def scenario():
        lim = AdaptiveLimiter(8)
        for _ in range(8):
            await lim.acquire()
        assert lim.active == 8
        blocked = asyncio.create_task(lim.acquire())
        await asyncio.sleep(0.05)
        assert not blocked.done()
        lim.release()
        await asyncio.wait_for(blocked, 2)
        lim.last_change = 0
        lim.on_flood(0)
        assert lim.limit == 4
        lim.on_flood(0)                 # same flood burst reported again: not halved twice
        assert lim.limit == 4
        lim.last_change = lim.flood_until = time.time() - 60
        lim.on_success()
        assert lim.limit == 5
    asyncio.run(scenario())


def test_rate_limiter_waits():
    async def scenario():
        r = RateLimiter()
        r.rate = 100_000
        r.ts = time.time()
        t0 = time.time()
        await r.consume(150_000)
        return time.time() - t0
    assert asyncio.run(scenario()) >= 1.0


def test_download_window(monkeypatch):
    noon = time.mktime((2026, 1, 1, 12, 0, 0, 0, 0, -1))
    night = time.mktime((2026, 1, 1, 2, 0, 0, 0, 0, -1))
    monkeypatch.setitem(settings._data, "download_window_start", "")
    monkeypatch.setitem(settings._data, "download_window_end", "")
    assert tasks.in_download_window(noon)
    monkeypatch.setitem(settings._data, "download_window_start", "23:00")
    monkeypatch.setitem(settings._data, "download_window_end", "07:00")
    assert tasks.in_download_window(night) and not tasks.in_download_window(noon)
    monkeypatch.setitem(settings._data, "download_window_start", "09:00")
    monkeypatch.setitem(settings._data, "download_window_end", "18:00")
    assert tasks.in_download_window(noon) and not tasks.in_download_window(night)


def test_workflow_report():
    from tgagent.extras import workflow_report
    from tgagent.workflow import workflows
    wf = workflows.start("rep-1", "tester", "Report me", "goal text")
    s, _ = workflows.begin_step(wf, "tg_list_files", {"chat": "x"})
    workflows.end_step(wf, s, True, {"chat": {"id": 1}, "files": []}, "0 files", 3)
    workflows.finish("rep-1", "all good")
    md = workflow_report(wf.id, [])
    assert "# Report me" in md and "tg_list_files" in md and "all good" in md


def test_version_compare():
    from tgagent.extras import _vtuple
    assert _vtuple("v1.1.0") > _vtuple("1.0.9") and _vtuple("1.10.0") > _vtuple("1.9.9")


def test_produced_refs_tolerates_counts():
    from tgagent.workflow import produced_refs
    assert produced_refs({"files": 3, "sample": [{"message_id": 9}]}) == {"m:9"}


def test_download_dir_problem(monkeypatch, tmp_path):
    monkeypatch.setitem(settings._data, "download_dir", str(tmp_path / "dl"))
    assert tasks.download_dir_problem() == ""
    monkeypatch.setitem(settings._data, "download_dir", "Q:\\nowhere" if __import__("os").name == "nt" else "/proc/forbidden/x")
    assert tasks.download_dir_problem() != ""
