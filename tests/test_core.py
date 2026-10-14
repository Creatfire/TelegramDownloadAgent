"""Offline unit tests: link parsing, file names, filters, workflow graph, local index, downloader, auth."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from telethon.tl import types

from tgagent import index, readers
from tgagent.tasks import safe_name
from tgagent.workflow import WorkflowManager, produced_refs, used_refs


# ---------------------------------------------------------------- link parsing
@pytest.mark.parametrize("ref, chat, msg, invite", [
    ("@durov", "durov", None, None),
    ("durov", "durov", None, None),
    ("https://t.me/durov/42", "durov", 42, None),
    ("t.me/s/durov", "durov", None, None),
    ("https://t.me/c/1005640892/7", -1001005640892, 7, None),
    ("https://t.me/c/1005640892/3/9", -1001005640892, 9, None),
    ("-1001005640892", -1001005640892, None, None),
    ("https://t.me/+AbCdEf", None, None, "AbCdEf"),
    ("https://t.me/joinchat/XyZ", None, None, "XyZ"),
    ("tg://resolve?domain=telegram&post=5", "telegram", 5, None),
])
def test_parse_ref(ref, chat, msg, invite):
    r = readers.parse_ref(ref)
    assert (r.chat, r.msg_id, r.invite) == (chat, msg, invite)


def test_safe_name():
    assert safe_name('a<b>c:"d"/e\\f|g?h*') == "a_b_c__d__e_f_g_h_"
    assert safe_name("name. ") == "name"
    long = "x" * 300 + ".mp4"
    out = safe_name(long)
    assert len(out) <= 150 and out.endswith(".mp4")


# ---------------------------------------------------------------- filters
def fake_msg(name="Movie.MP4", size=50 * 1024 * 1024, kind="video", text="", mid=1):
    f = SimpleNamespace(name=name, size=size, mime_type="video/mp4", ext="." + name.rsplit(".", 1)[-1].lower(),
                        duration=None, width=None, height=None)
    flags = {k: False for k in ("photo", "sticker", "gif", "video_note", "video", "voice", "audio", "document")}
    flags[kind] = True
    flags["document"] = True if kind != "photo" else False
    return SimpleNamespace(id=mid, file=f, message=text, date=datetime(2026, 1, 1, tzinfo=timezone.utc), **flags)


def test_file_filter():
    m = fake_msg()
    assert readers.FileFilter().match(m)["kind"] == "video"
    assert readers.FileFilter(types_=["audio"]).match(m) is None
    assert readers.FileFilter(name_contains="movie").match(m)
    assert readers.FileFilter(extensions=["mp4"]).match(m)
    assert readers.FileFilter(extensions=["zip"]).match(m) is None
    assert readers.FileFilter(min_size_mb=100).match(m) is None
    assert readers.FileFilter(max_size_mb=100).match(m)


# ---------------------------------------------------------------- workflow graph
def test_refs():
    res = {"chat": {"id": -100123, "username": "Chan"}, "files": [{"message_id": 5}, {"message_id": 6}]}
    assert {"c:-100123", "c:chan", "m:5", "m:6"} <= produced_refs(res)
    assert used_refs({"chat": "@chan", "message_ids": [5]}) == {"c:chan", "m:5"}
    assert "m:9" in used_refs({"links": ["https://t.me/chan/9"]})


def test_workflow_parents_and_polls():
    wm = WorkflowManager()
    wf = wm.start("sess-1", "tester", "Demo")
    s1, _ = wm.begin_step(wf, "tg_resolve_chat", {"chat": "chan"})
    wm.end_step(wf, s1, True, {"id": -100123, "title": "Chan", "username": "chan", "type": "channel"}, "Chan", 5)
    s2, _ = wm.begin_step(wf, "tg_get_messages", {"chat": "-100123", "limit": 3})
    wm.end_step(wf, s2, True, {"chat": {"id": -100123}, "messages": [{"id": 77}]}, "", 5)
    s3, _ = wm.begin_step(wf, "tg_list_files", {"chat": "chan"})
    wm.end_step(wf, s3, True, {"chat": {"id": -100123, "username": "chan"}, "files": [{"message_id": 10}]}, "", 5)
    s4, _ = wm.begin_step(wf, "tg_get_message", {"chat": "chan", "message_id": 77})
    # message 77 came from step 2, the chat from step 3 → two data parents
    assert {p["id"] for p in s4.parents} == {s2.id, s3.id}
    assert all(p["kind"] == "data" for p in s4.parents)
    wm.end_step(wf, s4, True, {"id": 77, "date": "x"}, "", 5)
    s5, _ = wm.begin_step(wf, "tg_download", {"chat": "chan", "message_ids": [10]})
    wm.attach_tasks(s5, ["t1"])
    wm.end_step(wf, s5, True, {"queued": 1, "tasks": [{"task_id": "t1"}]}, "", 5)
    target, is_poll = wm.begin_step(wf, "tg_tasks", {"task_ids": ["t1"]})
    assert is_poll and target.id == s5.id and target.polls == 1
    wm.begin_step(wf, "tg_tasks", {"task_ids": ["t1"]})
    assert s5.polls == 2 and len(wf.steps) == 5
    done = wm.finish("sess-1", "ok")
    assert done.status == "done" and wm.detail(wf.id)["workflow"]["steps"] == 5


def test_implicit_workflow():
    wm = WorkflowManager()
    wf, created = wm.current("sess-2", "tester")
    assert created and not wf.explicit
    wf2, created2 = wm.current("sess-2", "tester")
    assert wf2 is wf and not created2


# ---------------------------------------------------------------- local index
def test_index_search_and_compare():
    def add(chat_id, mid, name, size):
        ent = types.Channel(id=abs(chat_id) - 1000000000000, title=f"C{chat_id}", photo=types.ChatPhotoEmpty(),
                            date=datetime(2026, 1, 1, tzinfo=timezone.utc), broadcast=True, access_hash=1, username=None)
        msg = SimpleNamespace(id=mid, date=datetime(2026, 1, 1, tzinfo=timezone.utc), message="", document=SimpleNamespace(id=mid), photo=None)
        index.add("acc", ent, msg, {"kind": "document", "name": name, "size": size, "ext": name.rsplit(".", 1)[-1], "mime": None})
    add(-1000000000001, 1, "Game One.zip", 100)
    add(-1000000000001, 2, "Game Two.zip", 200)
    add(-1000000000002, 1, "game one.zip", 100)
    add(-1000000000002, 3, "Other.7z", 300)
    index.flush()
    r = index.search("acc", "game")
    assert r["matched"] == 3
    assert index.search("acc", extensions=["7z"])["matched"] == 1
    c = index.compare("acc", -1000000000001, -1000000000002, by="name_size")
    assert (c["in_both"]["count"], c["only_in_a"]["count"], c["only_in_b"]["count"]) == (1, 1, 1)


# ---------------------------------------------------------------- downloader
class FakeSender:
    def __init__(self, data: bytes, fail: set):
        self.data, self.fail, self.connected = data, fail, True

    def is_connected(self):
        return self.connected

    async def send(self, req):
        if req.offset in self.fail:
            self.fail.discard(req.offset)
            raise asyncio.IncompleteReadError(b"", 8)   # what a dropping proxy produces
        return types.upload.File(type=types.storage.FileUnknown(), mtime=0, bytes=self.data[req.offset:req.offset + req.limit])


class FakePool:
    def __init__(self, data, fail):
        self.data, self.fail, self.created = data, fail, 0

    async def acquire(self, dc):
        self.created += 1
        return FakeSender(self.data, self.fail)

    def release(self, dc, s):
        pass

    async def discard(self, s):
        s.connected = False


def test_parallel_download_retries_and_resume(tmp_path, monkeypatch):
    from tgagent import fastdl
    real_sleep = asyncio.sleep
    monkeypatch.setattr(fastdl.asyncio, "sleep", lambda *_: real_sleep(0))
    data = bytes(range(256)) * 4096 + b"tail"          # ~1 MB + 4 bytes → 5 parts of 256 KB
    doc = types.Document(id=1, access_hash=2, file_reference=b"", date=None, mime_type="x", size=len(data), dc_id=2, attributes=[])
    part = tmp_path / "f.bin.part"
    got = []
    pool = FakePool(data, fail={262144, 524288})
    asyncio.run(fastdl.parallel_download(pool, doc, part, 3, 262144, got.append, None))
    assert part.read_bytes() == data and sum(got) == len(data)
    assert not (tmp_path / "f.bin.part.json").exists()

    # Resume data saying everything is done must finish without opening a connection
    part2 = tmp_path / "g.bin.part"
    part2.write_bytes(data)
    (tmp_path / "g.bin.part.json").write_text(f'{{"id": 1, "size": {len(data)}, "part_size": 262144, "done": [0,1,2,3,4]}}')
    pool2 = FakePool(data, fail=set())
    asyncio.run(fastdl.parallel_download(pool2, doc, part2, 3, 262144, lambda n: None, None))
    assert pool2.created == 0 and not (tmp_path / "g.bin.part.json").exists()


# ---------------------------------------------------------------- auth / local guard
def test_http_guard():
    from fastapi.testclient import TestClient
    from tgagent import auth
    from tgagent.config import PORT
    from tgagent.server import app
    c = TestClient(app, base_url=f"http://127.0.0.1:{PORT}")
    assert c.get("/api/tools").status_code == 401
    ok = c.get("/api/tools", headers={"Authorization": f"Bearer {auth.get_token()}"})
    assert ok.status_code == 200 and any(t["name"] == "tg_start_workflow" for t in ok.json())
    assert c.get("/api/tools", headers={"host": "evil.com"}).status_code == 403
    # cookie-authenticated writes also need the custom header
    c.cookies.set(auth.COOKIE, auth.get_token())
    assert c.post("/api/settings", json={}).status_code == 403
    assert c.post("/api/settings", json={}, headers={"X-TGA": "1"}).status_code == 200
