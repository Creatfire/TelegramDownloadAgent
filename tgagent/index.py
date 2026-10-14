"""Local file index (SQLite). Every file the service sees while listing, exporting or watching is
recorded, so agents can search, total up and compare channels without asking Telegram again."""
from __future__ import annotations

import re
import time
from typing import Any

from .db import db

_buffer: list[tuple] = []
_chat_meta: dict[tuple[str, int], dict] = {}
FLUSH_AT = 200


def add(account: str, entity, msg, fi: dict) -> None:
    from .readers import chat_brief, iso
    b = chat_brief(entity)
    _chat_meta[(account, b["id"])] = b
    doc = msg.document or msg.photo
    _buffer.append((account, b["id"], msg.id, iso(msg.date), fi["kind"], fi["name"], fi["name"].lower(),
                    fi["size"], (fi.get("ext") or "").lower(), fi.get("mime"), fi.get("duration"),
                    (msg.message or "")[:300], getattr(doc, "id", None)))
    if len(_buffer) >= FLUSH_AT:
        flush()


def flush(scanned_up_to: dict[tuple[str, int], int] | None = None) -> None:
    rows = _buffer[:]
    _buffer.clear()
    db.executemany("INSERT OR REPLACE INTO files (account, chat_id, message_id, date, kind, name, name_lc, size, ext,"
                   " mime, duration, caption, file_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    touched = {(r[0], r[1]) for r in rows} | set(scanned_up_to or {})
    for acc, cid in touched:
        b = _chat_meta.get((acc, cid), {})
        agg = db.one("SELECT COUNT(*) n, COALESCE(SUM(size),0) s FROM files WHERE account=? AND chat_id=?", (acc, cid))
        prev = db.one("SELECT * FROM chats WHERE account=? AND chat_id=?", (acc, cid)) or {}
        max_id = max(prev.get("max_scanned_id") or 0, (scanned_up_to or {}).get((acc, cid), 0))
        db.upsert("chats", {"account": acc, "chat_id": cid, "title": b.get("title") or prev.get("title"),
                            "username": b.get("username") or prev.get("username"),
                            "type": b.get("type") or prev.get("type"), "files": agg["n"], "total_size": agg["s"],
                            "max_scanned_id": max_id, "full_scan": prev.get("full_scan", 0), "updated": time.time()})


def mark_full_scan(account: str, chat_id: int, max_id: int) -> None:
    flush({(account, chat_id): max_id})
    db.execute("UPDATE chats SET full_scan=1 WHERE account=? AND chat_id=?", (account, chat_id))


def chat_state(account: str, chat_id: int) -> dict | None:
    return db.one("SELECT * FROM chats WHERE account=? AND chat_id=?", (account, chat_id))


def status(account: str | None = None) -> list[dict]:
    if account:
        return db.all("SELECT * FROM chats WHERE account=? ORDER BY updated DESC", (account,))
    return db.all("SELECT * FROM chats ORDER BY updated DESC")


def _row(r: dict, titles: dict) -> dict:
    out = {k: r[k] for k in ("chat_id", "message_id", "date", "kind", "name", "size", "ext") if r.get(k) is not None}
    t = titles.get(r["chat_id"])
    if t:
        out["chat"] = t["title"]
        if t.get("username"):
            out["link"] = f"https://t.me/{t['username']}/{r['message_id']}"
        elif str(r["chat_id"]).startswith("-100"):
            out["link"] = f"https://t.me/c/{str(r['chat_id'])[4:]}/{r['message_id']}"
    if r.get("caption"):
        out["caption"] = r["caption"][:120]
    from .readers import split_info
    arc = split_info(r["name"])
    if arc:
        out["archive"] = arc
    if r.get("downloaded"):
        out["downloaded"] = True
    return out


def _titles(account: str | None) -> dict:
    return {c["chat_id"]: c for c in status(account)}


def search(account: str | None, query: str = "", chat_ids: list[int] | None = None, kinds: list[str] | None = None,
           extensions: list[str] | None = None, min_size: int | None = None, max_size: int | None = None,
           sort: str = "date", limit: int = 100) -> dict:
    where, params = [], []
    if account:
        where.append("account=?"); params.append(account)
    for word in (query or "").lower().split():
        where.append("(name_lc LIKE ? OR LOWER(caption) LIKE ?)"); params += [f"%{word}%", f"%{word}%"]
    if chat_ids:
        where.append(f"chat_id IN ({','.join('?' * len(chat_ids))})"); params += chat_ids
    if kinds:
        where.append(f"kind IN ({','.join('?' * len(kinds))})"); params += kinds
    if extensions:
        exts = [e.lower().lstrip(".") for e in extensions]
        where.append(f"ext IN ({','.join('?' * len(exts))})"); params += exts
    if min_size:
        where.append("size >= ?"); params.append(min_size)
    if max_size:
        where.append("size <= ?"); params.append(max_size)
    w = ("WHERE " + " AND ".join(where)) if where else ""
    order = {"size": "size DESC", "name": "name_lc ASC", "date": "date DESC"}.get(sort, "date DESC")
    agg = db.one(f"SELECT COUNT(*) n, COALESCE(SUM(size),0) s FROM files {w}", params)
    rows = db.all(f"SELECT *, EXISTS(SELECT 1 FROM downloads d WHERE d.file_id = files.file_id) AS downloaded "
                  f"FROM files {w} ORDER BY {order} LIMIT ?", params + [max(1, min(int(limit), 1000))])
    titles = _titles(account)
    out = [_row(r, titles) for r in rows]
    from .readers import archive_sets
    return {"matched": agg["n"], "total_size": agg["s"], "files": out,
            "archive_sets": [{k: v for k, v in g.items() if k != "message_ids"} for g in archive_sets(out)]}


_STEM_RE = re.compile(r"[\s_\-\.\[\]\(\)【】（）]+")


def _key(r: dict, by: str) -> Any:
    if by == "file":           # identical Telegram file (forwarded copies share the document id)
        return r["file_id"] or (r["name_lc"], r["size"])
    if by == "name_size":
        return (r["name_lc"], r["size"])
    if by == "stem":           # name without extension and punctuation
        stem = r["name_lc"].rsplit(".", 1)[0] if "." in r["name_lc"] else r["name_lc"]
        return _STEM_RE.sub("", stem)
    return r["name_lc"]


def compare(account: str | None, chat_a: int, chat_b: int, by: str = "name_size", sample: int = 30) -> dict:
    def load(cid):
        q = "SELECT * FROM files WHERE chat_id=?" + (" AND account=?" if account else "")
        return db.all(q, (cid, account) if account else (cid,))
    a, b = load(chat_a), load(chat_b)
    ka = {}
    for r in a:
        ka.setdefault(_key(r, by), r)
    kb = {}
    for r in b:
        kb.setdefault(_key(r, by), r)
    both = [k for k in ka if k in kb]
    only_a = [k for k in ka if k not in kb]
    only_b = [k for k in kb if k not in ka]
    titles = _titles(account)
    size = lambda keys, m: sum(m[k]["size"] or 0 for k in keys)
    return {
        "by": by,
        "a": {"chat_id": chat_a, "title": titles.get(chat_a, {}).get("title"), "files": len(a), "unique_keys": len(ka)},
        "b": {"chat_id": chat_b, "title": titles.get(chat_b, {}).get("title"), "files": len(b), "unique_keys": len(kb)},
        "in_both": {"count": len(both), "size": size(both, ka), "sample": [_row(ka[k], titles) for k in both[:sample]]},
        "only_in_a": {"count": len(only_a), "size": size(only_a, ka), "sample": [_row(ka[k], titles) for k in only_a[:sample]]},
        "only_in_b": {"count": len(only_b), "size": size(only_b, kb), "sample": [_row(kb[k], titles) for k in only_b[:sample]]},
    }
