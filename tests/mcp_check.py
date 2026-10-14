"""MCP connectivity check against a running TG Agent: connects over HTTP and over the stdio bridge,
lists the tools and calls one.

    python tests/mcp_check.py [tool] [json-args]
    python tests/mcp_check.py tg_resolve_chat "{\"chat\": \"telegram\"}"
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
from mcp.client.stdio import StdioServerParameters, stdio_client  # noqa: E402
from mcp.client.streamable_http import streamable_http_client  # noqa: E402

from tgagent.auth import get_token  # noqa: E402

PORT = os.environ.get("TGA_PORT", "17865")
TOOL = sys.argv[1] if len(sys.argv) > 1 else "tg_list_accounts"
ARGS = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}


async def exercise(label: str, streams) -> None:
    read, write = streams[0], streams[1]
    async with ClientSession(read, write, client_info=types.Implementation(name=f"mcp-check-{label}", version="1")) as s:
        await s.initialize()
        tools = await s.list_tools()
        print(f"[{label}] {len(tools.tools)} tools: {', '.join(t.name for t in tools.tools)}")
        res = await s.call_tool(TOOL, ARGS)
        text = res.content[0].text if res.content else ""
        print(f"[{label}] {TOOL} is_error={res.is_error}\n{text[:1200]}\n")


async def main() -> None:
    client = httpx2.AsyncClient(headers={"Authorization": f"Bearer {get_token()}"}, timeout=60, trust_env=False)
    async with streamable_http_client(f"http://127.0.0.1:{PORT}/mcp", http_client=client) as streams:
        await exercise("http", streams)
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "mcp_stdio.py")])
    async with stdio_client(params) as streams:
        await exercise("stdio", streams)


if __name__ == "__main__":
    anyio.run(main)
