"""Local message archive: message text the service has seen is stored in SQLite with full-text search,
so agents can search history (titles, versions, passwords…) without asking Telegram again."""
from __future__ import annotations

import re
import time

from .db import db

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    account TEXT, chat_id INTEGER, message_id INTEGER, date TEXT, sender TEXT, text TEXT,
    file_name TEXT, grouped_id INTEGER, PRIMARY KEY (account, chat_id, message_id)
);
CREATE INDEX IF NOT EXISTS ix_msg_chat ON messages(chat_id, message_id);
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    text, file_name, content='messages', content_rowid='rowid', tokenize='trigram'
);
CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, text, file_name) VALUES (new.rowid, new.text, new.file_name);
END;
CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, text, file_name) VALUES ('delete', old.rowid, old.text, old.file_name);
END;
CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, text, file_name) VALUES ('delete', old.rowid, old.text, old.file_name);
    INSERT INTO messages_fts(rowid, text, file_name) VALUES (new.rowid, new.text, new.file_name);
END;
"""
db.conn.executescript(SCHEMA)

_buffer: list[tuple] = []
FLUSH_AT = 200


def add(account: str, chat_id: int, msg) -> None:
    """Remember a message (text or caption). Messages without text and without a file are skipped."""
    text = msg.message or ""
    f = getattr(msg, "file", None)
    name = getattr(f, "name", None) if f else None
    if not text and not name:
        return
    sender = ""
    try:
        s = msg.sender
        sender = (getattr(s, "title", None) or " ".join(x for x in (getattr(s, "first_name", None), getattr(s, "last_name", None)) if x)
                  or getattr(msg, "post_author", "") or "") if s else (getattr(msg, "post_author", "") or "")
    except Exception:
        pass
    date = msg.date.strftime("%Y-%m-%dT%H:%M:%SZ") if msg.date else None
    _buffer.append((account, chat_id, msg.id, date, sender, text, name or "", msg.grouped_id))
    if len(_buffer) >= FLUSH_AT:
        flush()


def flush() -> None:
    rows = _buffer[:]
    _buffer.clear()
    db.executemany("INSERT OR REPLACE INTO messages (account, chat_id, message_id, date, sender, text, file_name, grouped_id)"
                   " VALUES (?,?,?,?,?,?,?,?)", rows)


def count(account: str | None = None) -> dict:
    q = "SELECT COUNT(*) n, COUNT(DISTINCT chat_id) c FROM messages" + (" WHERE account=?" if account else "")
    return db.one(q, (account,) if account else ())


def _fts_query(words: list[str]) -> str:
    return " AND ".join('"' + w.replace('"', '""') + '"' for w in words)


def search(account: str | None, query: str, chat_ids: list[int] | None = None, since: str | None = None,
           until: str | None = None, limit: int = 30) -> dict:
    """Words of 3+ characters use the FTS index; shorter ones (e.g. 2-character Chinese words) fall back to LIKE."""
    words = [w for w in re.split(r"\s+", (query or "").strip()) if w]
    long_w = [w for w in words if len(w) >= 3]
    short_w = [w for w in words if len(w) < 3]
    where, params = [], []
    base = "SELECT m.*, m.rowid AS rid FROM messages m"
    if long_w:
        base = ("SELECT m.*, m.rowid AS rid, snippet(messages_fts, 0, '[', ']', '…', 12) AS snip "
                "FROM messages_fts JOIN messages m ON m.rowid = messages_fts.rowid")
        where.append("messages_fts MATCH ?")
        params.append(_fts_query(long_w))
    for w in short_w:
        where.append("(m.text LIKE ? OR m.file_name LIKE ?)")
        params += [f"%{w}%", f"%{w}%"]
    if account:
        where.append("m.account=?"); params.append(account)
    if chat_ids:
        where.append(f"m.chat_id IN ({','.join('?' * len(chat_ids))})"); params += chat_ids
    if since:
        where.append("m.date >= ?"); params.append(since)
    if until:
        where.append("m.date <= ?"); params.append(until)
    sql = base + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY m.date DESC LIMIT ?"
    rows = db.all(sql, params + [max(1, min(int(limit or 30), 200))])
    titles = {c["chat_id"]: c for c in db.all("SELECT chat_id, title, username FROM chats")}
    out = []
    for r in rows:
        t = titles.get(r["chat_id"], {})
        item = {"chat_id": r["chat_id"], "chat": t.get("title"), "message_id": r["message_id"], "date": r["date"],
                "text": (r.get("snip") or r["text"] or "")[:400]}
        if r["file_name"]:
            item["file_name"] = r["file_name"]
        if t.get("username"):
            item["link"] = f"https://t.me/{t['username']}/{r['message_id']}"
        elif str(r["chat_id"]).startswith("-100"):
            item["link"] = f"https://t.me/c/{str(r['chat_id'])[4:]}/{r['message_id']}"
        out.append(item)
    return {"query": query, "count": len(out), "messages": out}


def neighbours(account: str, chat_id: int, message_id: int, around: int = 5) -> list[dict]:
    return db.all("SELECT * FROM messages WHERE account=? AND chat_id=? AND message_id BETWEEN ? AND ? ORDER BY message_id",
                  (account, chat_id, message_id - around, message_id + around))


def posts(account: str | None, chat_id: int, limit: int = 500) -> list[dict]:
    q = "SELECT * FROM messages WHERE chat_id=?" + (" AND account=?" if account else "") + " AND text != '' ORDER BY message_id DESC LIMIT ?"
    return db.all(q, (chat_id, account, limit) if account else (chat_id, limit))


# ---------------------------------------------------------------- information extraction
_PW = re.compile(r"(?:解压密码|解壓密碼|压缩密码|密码|密碼|提取码|提取碼|password|passwd|pwd|pass)\s*[:：=]?\s*[「“\"']?([^\s「」“”\"'，,。；;]{2,64})", re.I)
_VER = re.compile(r"(?<![\w.])(?:v|ver\.?|version\s*)?(\d+(?:\.\d+){1,3}[a-z]?)(?![\w.])", re.I)
_LINK = re.compile(r"(?:https?://|t\.me/)[^\s<>\"'）)]+", re.I)
_SIZE = re.compile(r"(\d+(?:\.\d+)?)\s*(KB|MB|GB|TB|K|M|G)\b", re.I)


def extract_info(text: str) -> dict:
    """Pull passwords, versions, links and sizes out of free text (captions, intro posts)."""
    text = text or ""
    info: dict = {}
    pws = list(dict.fromkeys(m.group(1) for m in _PW.finditer(text)))
    if pws:
        info["passwords"] = pws[:5]
    vers = list(dict.fromkeys(m.group(1) for m in _VER.finditer(text) if "." in m.group(1)))
    if vers:
        info["versions"] = vers[:5]
    links = list(dict.fromkeys(m.group(0).rstrip(".,，。") for m in _LINK.finditer(text)))
    if links:
        info["links"] = links[:10]
    sizes = list(dict.fromkeys(f"{m.group(1)} {m.group(2).upper()}" for m in _SIZE.finditer(text)))
    if sizes:
        info["sizes"] = sizes[:5]
    first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    if first:
        info["title"] = first[:120]
    return info


# ---------------------------------------------------------------- matching intro posts with files
_STRIP = re.compile(r"\.(7z|zip|rar|tar|gz|exe|apk|iso|mp4|mkv|pdf)(\.\d{2,4})?$|\.part\d+\.rar$", re.I)
_TOKEN = re.compile(r"[a-z0-9]+|[぀-ヿ㐀-鿿]", re.I)
_NOISE = {"官方中文", "中文", "汉化", "漢化", "官中", "pc", "安卓", "直装", "apk", "ai", "版", "最新", "合集"}


def _tokens(s: str) -> set[str]:
    s = _STRIP.sub("", (s or "").lower())
    toks = _TOKEN.findall(s)
    out = set()
    for i, t in enumerate(toks):
        if len(t) == 1 and "぀" <= t <= "鿿":
            if i + 1 < len(toks) and len(toks[i + 1]) == 1:
                out.add(t + toks[i + 1])          # CJK bigrams
        elif t not in _NOISE and len(t) > 1:
            out.add(t)
    return out


def similarity(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    return round(inter / min(len(ta), len(tb)) * 0.7 + inter / len(ta | tb) * 0.3, 3)
