"""Offline tests for v1.2: message archive, info extraction, matching, output shaping, recipes, quotas, lanes."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from tgagent import archive, assist, recipes
from tgagent.config import settings
from tgagent.tools import shape_output


def _msg(mid, text, name=None):
    f = SimpleNamespace(name=name) if name else None
    return SimpleNamespace(id=mid, message=text, file=f, sender=None, post_author="",
                           date=datetime(2026, 1, 1, tzinfo=timezone.utc), grouped_id=None)


def test_archive_search_long_and_short_words():
    archive.add("acc", -1001, _msg(1, "初恋 master-up 汉化版\n解压密码：abc123"))
    archive.add("acc", -1001, _msg(2, "另一个游戏 v2.0", "other.7z"))
    archive.flush()
    assert archive.search("acc", "master")["count"] == 1          # FTS (3+ chars)
    assert archive.search("acc", "密码")["count"] == 1            # LIKE fallback (2 chars)
    assert archive.search("acc", "other.7z")["messages"][0]["file_name"] == "other.7z"


def test_extract_info():
    info = archive.extract_info("百日战纪 v1.0.3 官方中文\n解压密码: nightcat\n大小 2.3GB\nhttps://t.me/x/5")
    assert info["passwords"] == ["nightcat"] and info["versions"] == ["1.0.3"]
    assert info["sizes"] == ["2.3 GB"] and info["links"] == ["https://t.me/x/5"]


def test_similarity_pairs_titles_with_files():
    good = archive.similarity("百日战纪 最终防卫学园 官方中文", "PCMedia_Vision百日战纪_最终防卫学园_官方中文_7z.001")
    bad = archive.similarity("百日战纪 最终防卫学园", "初恋master-up_机翻.7z")
    assert good > 0.6 and bad < 0.2


def test_shape_output():
    res = {"files": [{"message_id": 1, "name": "a", "size": 3, "extra": {"x": 1}}], "count": 1}
    assert shape_output(res, ["name"], "json")["files"] == [{"name": "a"}]
    c = shape_output(res, None, "compact")["files"]
    assert c["columns"] == ["message_id", "name", "size"] and c["rows"] == [[1, "a", 3]]


def test_recipe_resolution():
    results = [{"task_id": "t1"}, {"tasks": [{"task_id": "a"}, {"task_id": "b"}]}]
    args = {"chat": "{chat}", "limit": "{count}", "task_ids": "{{2.tasks[*].task_id}}", "x": ["{{1.task_id}}"]}
    out = recipes._clean(recipes._resolve(args, {"chat": "telegram", "count": "5"}, results))
    assert out == {"chat": "telegram", "limit": 5, "task_ids": ["a", "b"], "x": ["t1"]}


def test_recipe_from_workflow():
    detail = {"workflow": {"title": "t", "goal": "g"}, "steps": [
        {"tool": "tg_start_workflow", "args": {}, "status": "done", "task_ids": []},
        {"tool": "tg_download", "args": {"chat": "chanA", "message_ids": [5]}, "status": "done", "task_ids": ["x1", "x2"]},
        {"tool": "tg_wait_tasks", "args": {"task_ids": ["x1", "x2"]}, "status": "done", "task_ids": []},
        {"tool": "tg_list_files", "args": {"chat": "chanB"}, "status": "done", "task_ids": []},
    ]}
    r = recipes.from_workflow(detail, "My recipe")
    assert [s["tool"] for s in r["steps"]] == ["tg_download", "tg_wait_tasks", "tg_list_files"]
    assert r["steps"][0]["args"]["chat"] == "{chat1}" and r["steps"][2]["args"]["chat"] == "{chat2}"
    assert r["steps"][1]["args"]["task_ids"] == "{{1.tasks[*].task_id}}"
    assert [p["name"] for p in r["params"]] == ["chat1", "chat2"]
    recipes.delete(r["id"])


def test_quotas(monkeypatch):
    monkeypatch.setitem(settings._data, "agent_limits", {"bot-x": {"daily_requests": 2, "chats": ["allowed"]}})
    assist.check_request("bot-x", ["allowed"])
    for _ in range(2):
        assist.count_request("bot-x")
    try:
        assist.check_request("bot-x", ["allowed"])
        raise AssertionError("quota not enforced")
    except assist.QuotaError:
        pass
    monkeypatch.setitem(settings._data, "agent_limits", {"bot-y": {"chats": ["allowed"]}})
    try:
        assist.check_request("bot-y", ["other"])
        raise AssertionError("chat allow-list not enforced")
    except assist.QuotaError:
        pass
    assist.check_request("console", ["anything"])


def test_questions_answer():
    async def scenario():
        task = asyncio.create_task(assist.questions.ask("bot", "Which one?", ["A", "B"], False, 30))
        await asyncio.sleep(0.05)
        q = assist.questions.pending()[-1]
        assist.questions.answer(q["id"], "B")
        return await task
    assert asyncio.run(scenario()) == {"answered": True, "answer": "B"}


def test_lanes_follow_chats():
    from tgagent.workflow import WorkflowManager
    wm = WorkflowManager()
    wf = wm.start("lane-1", "tester", "Lanes")
    a, _ = wm.begin_step(wf, "tg_get_messages", {"chat": "introchan"})
    wm.end_step(wf, a, True, {"chat": {"id": -1009, "title": "Intro", "username": "introchan"}, "messages": []}, "", 1)
    b, _ = wm.begin_step(wf, "tg_list_files", {"chat": "fileschan"})
    m, _ = wm.begin_step(wf, "tg_match_posts", {"intro_chat": "introchan", "files_chat": "fileschan"})
    assert a.lanes[0] == {"key": "c:-1009", "title": "Intro"}
    assert b.lanes[0]["key"] == "c:fileschan"
    assert len(m.lanes) == 2 and m.lanes[0]["key"] == "c:-1009"


def test_extract_with_7zip(tmp_path):
    import subprocess
    import pytest
    from tgagent import postproc
    exe = postproc.sevenzip()
    if not exe:
        pytest.skip("7-Zip not installed")
    (tmp_path / "hello.txt").write_text("hi", "utf-8")
    arc = tmp_path / "pack.7z"
    subprocess.run([exe, "a", str(arc), str(tmp_path / "hello.txt"), "-psecret", "-mhe=on", "-bso0", "-bsp0"], check=True)
    ok, msg, _ = asyncio.run(postproc.run_7z(arc, "wrong", True, lambda p: None))
    assert not ok
    ok, msg, dest = asyncio.run(postproc.run_7z(arc, "secret", False, lambda p: None))
    assert ok and (dest / "hello.txt").read_text("utf-8") == "hi"
