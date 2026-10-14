"""Entry point.

    tg-agent [--no-browser]     start the service and open the console
    tg-agent token              print the access token (for MCP client configuration)
    tg-agent mcp                run the stdio MCP bridge
"""
from __future__ import annotations

import logging
import socket
import sys
import threading
import webbrowser

import httpx
import uvicorn

from . import __version__, auth
from .config import DATA_DIR, HOST, PORT


def _already_running() -> bool:
    try:
        r = httpx.get(f"http://{HOST}:{PORT}/api/tools", timeout=2, trust_env=False,
                      headers={"Authorization": f"Bearer {auth.get_token()}"})
        return r.status_code == 200
    except httpx.HTTPError:
        return False


def main() -> None:
    args = sys.argv[1:]
    if args[:1] == ["token"]:
        print(auth.get_token())
        return
    if args[:1] == ["mcp"]:
        from .mcp_stdio import main as bridge
        bridge()
        return

    token = auth.get_token()
    url = f"http://{HOST}:{PORT}"
    console = f"{url}/?token={token}"
    open_browser = "--no-browser" not in args
    if _already_running():
        print(f"TG Agent is already running: {console}")
        if open_browser:
            webbrowser.open(console)
        return
    with socket.socket() as s:
        if s.connect_ex((HOST, PORT)) == 0:
            print(f"Port {PORT} is used by another program. Set TGA_PORT to another port, e.g. TGA_PORT=17866")
            sys.exit(1)

    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    print(f"TG Agent {__version__}")
    print(f"  Console : {console}")
    print(f"  MCP     : {url}/mcp   (header  Authorization: Bearer {token})")
    print(f"  Data    : {DATA_DIR}")
    print("Close this window or press Ctrl+C to stop.")
    if open_browser:
        threading.Timer(1.5, lambda: webbrowser.open(console)).start()
    from .server import app
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


