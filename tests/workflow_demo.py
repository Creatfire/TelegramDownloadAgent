"""Simulates an AI agent session over MCP so the Workflows page can be checked by eye.

It starts a workflow, resolves a public channel, lists a few files, asks for a download that is forced to
need approval (approval limit temporarily lowered), rejects it, polls tasks and finishes the workflow.
Nothing is downloaded. Uses only a handful of Telegram requests.

    python tests/workflow_demo.py [channel]          (default: telegram)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import anyio  # noqa: E402
import httpx2  # noqa: E402
import mcp_types as types  # noqa: E402
from mcp.client.session import ClientSession  # noqa: E402
from mcp.client.streamable_http import streamable_http_client  # noqa: E402

from tgagent.auth import get_token  # noqa: E402

PORT = os.environ.get("TGA_PORT", "17865")
BASE = f"http://127.0.0.1:{PORT}"
CHANNEL = sys.argv[1] if len(sys.argv) > 1 else "telegram"
HEADERS = {"Authorization": f"Bearer {get_token()}"}


async def main() -> None:
    async with httpx2.AsyncClient(headers=HEADERS, timeout=60, trust_env=False) as rest:
        old = (await rest.get(f"{BASE}/api/settings")).json()
        await rest.post(f"{BASE}/api/settings", json={"approval_size_gb": 0.000001})
        try:
            client = httpx2.AsyncClient(headers=HEADERS, timeout=120, trust_env=False)
            async with streamable_http_client(f"{BASE}/mcp", http_client=client) as (read, write, *_):
                async with ClientSession(read, write, client_info=types.Implementation(name="workflow-demo", version="1")) as s:
                    await s.initialize()

                    async def call(name, **args):
                        r = await s.call_tool(name, args)
                        text = r.content[0].text if r.content else ""
                        print(f"{'ERR' if r.is_error else 'ok '} {name}: {text[:160].replace(chr(10), ' ')}")
                        return json.loads(text) if not r.is_error else None

                    await call("tg_start_workflow", title=f"Check recent videos in @{CHANNEL}",
                               goal="List a few small videos and try to download one")
                    info = await call("tg_resolve_chat", chat=CHANNEL)
                    files = await call("tg_list_files", chat=str(info["id"]), types=["video"], max_size_mb=20, limit=3, scan_limit=300)
                    if files and files["files"]:
                        ids = [f["message_id"] for f in files["files"][:1]]
                        dl = await call("tg_download", chat=str(info["id"]), message_ids=ids)
                        if dl and dl.get("requires_approval"):
                            batch = dl["approval_batch"]
                            print("   -> approval required as expected; rejecting it")
                            await rest.post(f"{BASE}/api/approvals/{batch}", json={"approve": False})
                            await call("tg_tasks", task_ids=[t["task_id"] for t in dl["tasks"]])
                            await call("tg_tasks", task_ids=[t["task_id"] for t in dl["tasks"]])
                    await call("tg_search_files", query="", chats=[str(info["id"])], limit=3)
                    await call("tg_finish_workflow", summary="Listed recent videos; the download request was rejected (demo).")
        finally:
            await rest.post(f"{BASE}/api/settings", json={"approval_size_gb": old.get("approval_size_gb", 2.0)})


if __name__ == "__main__":
    anyio.run(main)
