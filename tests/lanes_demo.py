"""Simulates an agent working across two chats (an "intro" chat and a "files" chat) so the swim-lane workflow
view, cross-chat matching, questions and notes can be checked by eye. Nothing is downloaded.

    python tests/lanes_demo.py [intro_chat] [files_chat]      (defaults: durov telegram)
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx2  # noqa: E402
import mcp_types as types  # noqa: E402
from mcp.client.session import ClientSession  # noqa: E402
from mcp.client.streamable_http import streamable_http_client  # noqa: E402

from tgagent.auth import get_token  # noqa: E402

BASE = f"http://127.0.0.1:{os.environ.get('TGA_PORT', '17865')}"
H = {"Authorization": f"Bearer {get_token()}"}
INTRO = sys.argv[1] if len(sys.argv) > 1 else "durov"
FILES = sys.argv[2] if len(sys.argv) > 2 else "telegram"


async def answer_soon(rest: httpx2.AsyncClient) -> None:
    for _ in range(40):
        await asyncio.sleep(0.5)
        qs = (await rest.get(f"{BASE}/api/questions")).json()
        if qs:
            await asyncio.sleep(3)
            await rest.post(f"{BASE}/api/questions/{qs[-1]['id']}", json={"answer": qs[-1]["options"][0]})
            return


async def main() -> None:
    client = httpx2.AsyncClient(headers=H, timeout=200, trust_env=False)
    async with httpx2.AsyncClient(headers=H, timeout=30, trust_env=False) as rest, \
            streamable_http_client(f"{BASE}/mcp", http_client=client) as (r, w, *_), \
            ClientSession(r, w, client_info=types.Implementation(name="lanes-demo", version="1")) as s:
        await s.initialize()

        async def call(name, **args):
            res = await s.call_tool(name, args)
            text = res.content[0].text if res.content else ""
            print(("ERR " if res.is_error else "ok  ") + name + ": " + text[:150].replace("\n", " "))
            return None if res.is_error else json.loads(text)

        await call("tg_start_workflow", title=f"Pair posts in @{INTRO} with files in @{FILES}")
        await asyncio.gather(call("tg_get_messages", chat=FILES, limit=8, format="compact"),
                             call("tg_list_files", chat=INTRO, limit=5, scan_limit=60, format="compact"))
        info = await call("tg_resolve_chat", chat=FILES)
        await call("tg_match_posts", intro_chat=INTRO, files_chat=FILES, posts=10, min_score=0.2)
        files = await call("tg_search_files", chats=[str(info["id"])], limit=3) if info else None
        if files and files["files"]:
            await call("tg_file_context", chat=str(info["id"]), message_id=files["files"][0]["message_id"])
        asker = asyncio.create_task(answer_soon(rest))
        await call("tg_ask_user", question="Two versions match — which one should I download?",
                   options=["The newest", "The smallest"], timeout_s=60)
        await asker
        await call("tg_notes", action="set", chat=FILES, text="Demo note: video posts carry the file name in the caption.")
        await call("tg_search_archive", query="Telegram", limit=3, format="compact")
        await call("tg_finish_workflow", summary="Matched posts across two chats; the user chose the newest version (demo).")


if __name__ == "__main__":
    asyncio.run(main())
