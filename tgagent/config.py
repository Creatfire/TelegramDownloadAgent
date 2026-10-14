"""Paths and global settings (settings.json in the data directory)."""
from __future__ import annotations

import json
import locale
import os
import threading
from pathlib import Path
from typing import Any

PKG_DIR = Path(__file__).resolve().parent
ROOT = PKG_DIR.parent
# Source checkout (start.bat / start.sh): keep data next to the code. Installed package: ~/.tg-agent
_IS_CHECKOUT = (ROOT / "pyproject.toml").exists()
_DEFAULT_HOME = ROOT if _IS_CHECKOUT else Path.home() / ".tg-agent"

DATA_DIR = Path(os.environ.get("TGA_DATA_DIR") or (_DEFAULT_HOME / "data"))
SESSIONS_DIR = DATA_DIR / "sessions"
EXPORTS_DIR = DATA_DIR / "exports"
WEB_DIR = PKG_DIR / "web"
SETTINGS_FILE = DATA_DIR / "settings.json"
ACCOUNTS_FILE = DATA_DIR / "accounts.json"
ACTIVITY_FILE = DATA_DIR / "activity.jsonl"
TASKS_FILE = DATA_DIR / "tasks.json"
DB_FILE = DATA_DIR / "tg-agent.db"
TOKEN_FILE = DATA_DIR / "token"

HOST = "127.0.0.1"
PORT = int(os.environ.get("TGA_PORT", "17865"))


def _default_language() -> str:
    try:
        lang = (locale.getlocale()[0] or os.environ.get("LANG", "")).lower()
    except Exception:
        lang = ""
    return "zh" if lang.startswith(("zh", "chinese")) else "en"


DEFAULT_SETTINGS: dict[str, Any] = {
    "language": _default_language(),
    # Proxy used by new accounts; {"type": ""} means direct connection
    "default_proxy": {"type": ""},
    "download_dir": str(_DEFAULT_HOME / "downloads"),
    # File name template: {chat} {chat_id} {msg_id} {name} {date}
    "name_template": "{chat}/{msg_id}_{name}",
    "max_concurrent_files": 2,
    "connections_per_file": 4,
    "part_size_kb": 512,
    # Delay between batches when reading history (seconds), to stay clear of rate limits
    "read_wait_time": 0.5,
    "default_account": "",
    # AI-initiated downloads above these limits wait for approval in the console (0 = never ask)
    "approval_size_gb": 2.0,
    "approval_files": 50,
    # Seconds of inactivity after which an implicit (not explicitly started) workflow is closed
    "workflow_idle_seconds": 1800,
    # Global download speed limit in KB/s (0 = unlimited)
    "speed_limit_kbps": 0,
    # Only download between these local times ("HH:MM"; both empty = any time; may wrap midnight)
    "download_window_start": "",
    "download_window_end": "",
    # Skip files that were already downloaded (same Telegram file, e.g. forwarded to several channels)
    "dedupe_downloads": True,
    # Check GitHub for new releases once a day
    "check_updates": True,
}


class Settings:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data = dict(DEFAULT_SETTINGS)
        if SETTINGS_FILE.exists():
            try:
                self._data.update(json.loads(SETTINGS_FILE.read_text("utf-8")))
            except Exception:
                pass

    def get(self, key: str) -> Any:
        return self._data.get(key, DEFAULT_SETTINGS.get(key))

    def all(self) -> dict[str, Any]:
        return dict(self._data)

    def update(self, values: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            for k, v in values.items():
                if k in DEFAULT_SETTINGS:
                    self._data[k] = v
            SETTINGS_FILE.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), "utf-8")
        return self.all()


def ensure_dirs() -> None:
    for d in (DATA_DIR, SESSIONS_DIR, EXPORTS_DIR):
        d.mkdir(parents=True, exist_ok=True)


ensure_dirs()
settings = Settings()
