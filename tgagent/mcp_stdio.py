"""stdio MCP bridge for clients that only speak stdio (Codex, ZCode, Cursor…).
Each client conversation starts its own bridge process, which forwards calls to the running TG Agent
service together with a per-process session id, so the console can group calls per conversation.

    tg-agent-mcp            (installed)
    python -m tgagent.mcp_stdio
"""
from __future__ import annotations

import os
import uuid

import anyio
import httpx
from mcp.server.stdio import stdio_server

from .config import PORT, TOKEN_FILE
from .mcp_server import build_server, tool_dicts

BASE = os.environ.get("TGA_URL", f"http://127.0.0.1:{PORT}")
SESSION = f"stdio:{uuid.uuid4().hex[:12]}"
NOT_RUNNING = (f"TG Agent is not running ({BASE}). Ask the user to start it (start.bat / start.sh / tg-agent) and retry. "
               f"/ TG Agent 服务未运行，请让用户启动后重试。")


def _headers(agent: str) -> dict:
    token = os.environ.get("TGA_TOKEN") or (TOKEN_FILE.read_text("utf-8").strip() if TOKEN_FILE.exists() else "")
    return {"Authorization": f"Bearer {token}", "X-Agent": agent.encode("utf-8").hex(), "X-Session": SESSION}


async def list_fn():
    try:
        async with httpx.AsyncClient(timeout=10, trust_env=False) as c:
            r = await c.get(f"{BASE}/api/tools", headers=_headers("bridge"))
            r.raise_for_status()
            return r.json()
    except httpx.HTTPError:
        return tool_dicts()   # still expose the tools; calls will explain that the service is down


async def call_fn(name: str, args: dict, agent: str, _session: str):
    try:
        async with httpx.AsyncClient(timeout=600, trust_env=False) as c:
            r = await c.post(f"{BASE}/api/tools/{name}", json=args, headers=_headers(agent))
            if r.status_code == 401:
                return False, "TG Agent rejected the access token. Set TGA_TOKEN or run the bridge as the same user."
            data = r.json()
            return data.get("ok", False), data.get("result") if data.get("ok") else data.get("error")
    except httpx.ConnectError:
        return False, NOT_RUNNING
    except httpx.HTTPError as e:
        return False, f"Request to TG Agent failed: {e}"


async def _main():
    server = build_server(list_fn, call_fn)
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main():
    anyio.run(_main)


if __name__ == "__main__":
    main()
