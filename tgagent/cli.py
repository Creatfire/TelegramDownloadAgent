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
    server = uvicorn.Server(uvicorn.Config(app, host=HOST, port=PORT, log_level="warning"))
    if "--no-tray" not in args:
        _start_tray(server, console, token)
    server.run()


def _tray_image():
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((2, 2, 62, 62), radius=14, fill=(34, 30, 26, 255), outline=(232, 131, 58, 255), width=3)
    d.polygon([(14, 33), (50, 17), (43, 49), (32, 41), (26, 47), (26, 38), (42, 24), (22, 36)], fill=(232, 131, 58, 255))
    return img


def _start_tray(server, console: str, token: str) -> None:
    """System tray icon (Windows): open the console, pause all downloads, quit."""
    if sys.platform != "win32":
        return
    try:
        import pystray
    except ImportError:
        return

    def pause_all(icon, item):
        try:
            httpx.post(f"http://{HOST}:{PORT}/api/tasks/control", json={"action": "pause", "all": True},
                       headers={"Authorization": f"Bearer {token}"}, timeout=5, trust_env=False)
        except httpx.HTTPError:
            pass

    def quit_app(icon, item):
        icon.stop()
        server.should_exit = True

    icon = pystray.Icon("tg-agent", _tray_image(), f"TG Agent {__version__}", menu=pystray.Menu(
        pystray.MenuItem("Open console / 打开控制台", lambda i, it: webbrowser.open(console), default=True),
        pystray.MenuItem("Pause all downloads / 全部暂停", pause_all),
        pystray.MenuItem("Quit / 退出", quit_app),
    ))
    threading.Thread(target=icon.run, daemon=True).start()


