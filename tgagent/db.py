"""SQLite storage: workflow history (sessions / workflows / steps), local file index, watches."""
from __future__ import annotations

import json
import sqlite3
import threading
from typing import Any, Iterable

from .config import DB_FILE

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY, agent TEXT, transport TEXT, created REAL, last_active REAL
);
CREATE TABLE IF NOT EXISTS workflows (
    id TEXT PRIMARY KEY, session_id TEXT, agent TEXT, title TEXT, goal TEXT, explicit INTEGER,
    status TEXT, summary TEXT, created REAL, updated REAL, ended REAL, steps INTEGER DEFAULT 0, polls INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_wf_session ON workflows(session_id, created);
CREATE INDEX IF NOT EXISTS ix_wf_updated ON workflows(updated);
CREATE TABLE IF NOT EXISTS steps (
    id TEXT PRIMARY KEY, workflow_id TEXT, seq INTEGER, tool TEXT, args TEXT, status TEXT,
    summary TEXT, result TEXT, error TEXT, parents TEXT, produced TEXT, task_ids TEXT,
    polls INTEGER DEFAULT 0, ts REAL, ms INTEGER
);
CREATE INDEX IF NOT EXISTS ix_steps_wf ON steps(workflow_id, seq);

CREATE TABLE IF NOT EXISTS chats (
    account TEXT, chat_id INTEGER, title TEXT, username TEXT, type TEXT,
    files INTEGER DEFAULT 0, total_size INTEGER DEFAULT 0, max_scanned_id INTEGER DEFAULT 0,
    full_scan INTEGER DEFAULT 0, updated REAL, PRIMARY KEY (account, chat_id)
);
CREATE TABLE IF NOT EXISTS files (
    account TEXT, chat_id INTEGER, message_id INTEGER, date TEXT, kind TEXT, name TEXT, name_lc TEXT,
    size INTEGER, ext TEXT, mime TEXT, duration INTEGER, caption TEXT, file_id INTEGER,
    PRIMARY KEY (account, chat_id, message_id)
);
CREATE INDEX IF NOT EXISTS ix_files_name ON files(name_lc);
CREATE INDEX IF NOT EXISTS ix_files_size ON files(size);
CREATE INDEX IF NOT EXISTS ix_files_fid ON files(file_id);

CREATE TABLE IF NOT EXISTS downloads (
    file_id INTEGER, account TEXT, chat_id INTEGER, message_id INTEGER, chat_title TEXT, name TEXT,
    path TEXT, size INTEGER, finished REAL, PRIMARY KEY (account, chat_id, message_id)
);
CREATE INDEX IF NOT EXISTS ix_dl_fid ON downloads(file_id);

CREATE TABLE IF NOT EXISTS watches (
    id TEXT PRIMARY KEY, account TEXT, chat TEXT, chat_id INTEGER, chat_title TEXT, filters TEXT,
    interval_min INTEGER, subdir TEXT, enabled INTEGER, pending_approval INTEGER, last_message_id INTEGER,
    last_check REAL, last_error TEXT, downloaded INTEGER DEFAULT 0, created REAL, source TEXT
);
"""


class DB:
    def __init__(self) -> None:
        self.conn = sqlite3.connect(DB_FILE, check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA synchronous=NORMAL")
            self.conn.executescript(SCHEMA)

    def execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self.lock:
            return self.conn.execute(sql, tuple(params))

    def executemany(self, sql: str, rows: list[tuple]) -> None:
        if not rows:
            return
        with self.lock:
            self.conn.execute("BEGIN")
            try:
                self.conn.executemany(sql, rows)
                self.conn.execute("COMMIT")
            except Exception:
                self.conn.execute("ROLLBACK")
                raise

    def all(self, sql: str, params: Iterable[Any] = ()) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, tuple(params)).fetchall()]

    def one(self, sql: str, params: Iterable[Any] = ()) -> dict | None:
        with self.lock:
            r = self.conn.execute(sql, tuple(params)).fetchone()
            return dict(r) if r else None

    def upsert(self, table: str, row: dict) -> None:
        cols = ", ".join(row)
        marks = ", ".join("?" for _ in row)
        self.execute(f"INSERT OR REPLACE INTO {table} ({cols}) VALUES ({marks})", row.values())


def dumps(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, default=str)


def loads(s: str | None, default: Any = None) -> Any:
    if not s:
        return default
    try:
        return json.loads(s)
    except Exception:
        return default


db = DB()
