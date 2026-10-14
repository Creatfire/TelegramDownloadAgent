"""Understanding content: what a file is (its caption, nearby posts, passwords, versions) and which posts in an
intro channel describe which files in a download channel."""
from __future__ import annotations

from telethon import TelegramClient, utils
from telethon.tl import types

from . import archive, assist, readers
from .db import db
from .i18n import L


async def file_context(client: TelegramClient, account: str, link: str | None = None, chat: str | None = None,
                       message_id: int | None = None, around: int = 6, intro_chat: str | None = None) -> dict:
    if link:
        cr = readers.parse_ref(link)
        if not cr.msg_id:
            raise ValueError("The link has no message id")
        entity, message_id = await readers._entity(client, cr.chat), cr.msg_id
    else:
        if not chat or not message_id:
            raise ValueError("Provide link, or chat + message_id")
        entity = await readers.get_entity(client, chat)
    chat_id = utils.get_peer_id(entity)
    around = max(0, min(int(around or 6), 20))
    ids = list(range(max(1, int(message_id) - around), int(message_id) + around + 1))
    msgs = [m for m in await client.get_messages(entity, ids=ids) if m and not isinstance(m, types.MessageService)]
    for m in msgs:
        archive.add(account, chat_id, m)
    archive.flush()
    target = next((m for m in msgs if m.id == int(message_id)), None)
    if target is None:
        raise ValueError(f"Message {message_id} does not exist or is not accessible")
    fi = readers.file_info(target)
    nearby = []
    for m in msgs:
        if m.id == target.id:
            continue
        item = {"id": m.id, "offset": m.id - target.id}
        if m.message:
            item["text"] = m.message[:300]
        mf = readers.file_info(m)
        if mf:
            item["file"] = mf["name"]
        if m.grouped_id and m.grouped_id == target.grouped_id:
            item["same_album"] = True
        nearby.append(item)
    own = archive.extract_info(target.message or "")
    # Intro text usually sits just before the files: weight the closest earlier posts first
    pool = " \n".join(m.message for m in sorted(msgs, key=lambda m: (m.id > target.id, abs(m.id - target.id))) if m.message)
    out = {
        "chat": readers.chat_brief(entity), "message_id": target.id, "date": readers.iso(target.date),
        "link": readers.message_link(entity, target.id), "file": fi, "caption": target.message or "",
        "info": own, "info_from_nearby": {k: v for k, v in archive.extract_info(pool).items() if k != "title"},
        "nearby": nearby,
    }
    note = assist.get_note(account, chat_id)
    if note:
        out["chat_note"] = note["text"]
    if intro_chat and fi:
        name = (fi.get("archive") or {}).get("set") or fi["name"]
        intro = await readers.get_entity(client, intro_chat)
        cands = await _intro_posts(client, account, intro, 200)
        scored = sorted(((archive.similarity(p["text"].splitlines()[0] if p["text"] else "", name), p) for p in cands),
                        key=lambda x: -x[0])[:3]
        out["intro_matches"] = [{"message_id": p["message_id"], "score": sc, "text": p["text"][:400],
                                 "info": archive.extract_info(p["text"]),
                                 "link": readers.message_link(intro, p["message_id"])} for sc, p in scored if sc >= 0.3]
    return out


async def _intro_posts(client: TelegramClient, account: str, entity, want: int) -> list[dict]:
    """Recent text posts of an intro channel, from the archive; reads from Telegram only when the archive is thin."""
    chat_id = utils.get_peer_id(entity)
    posts = archive.posts(account, chat_id, want)
    if len(posts) < min(want, 20):
        async for m in client.iter_messages(entity, limit=want):
            if not isinstance(m, types.MessageService):
                archive.add(account, chat_id, m)
        archive.flush()
        posts = archive.posts(account, chat_id, want)
    return posts


async def match_posts(client: TelegramClient, account: str, intro_chat: str, files_chat: str, posts: int = 30,
                      min_score: float = 0.35, per_post: int = 3, query: str = "") -> dict:
    intro = await readers.get_entity(client, intro_chat)
    files_ent = await readers.get_entity(client, files_chat)
    files_id = utils.get_peer_id(files_ent)
    rows = db.all("SELECT message_id, name, size, kind FROM files WHERE account=? AND chat_id=?", (account, files_id))
    if not rows:
        return {"pairs": [], "hint": L("下载频道还没有索引。先调用 tg_index_chat 并用 tg_wait_tasks 等待完成。",
                                       "The files chat is not indexed yet. Call tg_index_chat and tg_wait_tasks first.")}
    groups: dict[str, dict] = {}
    for r in rows:
        si = readers.split_info(r["name"])
        key = (si["set"] if si else r["name"])
        g = groups.setdefault(key.lower(), {"name": key, "size": 0, "message_ids": [], "parts": 0})
        g["size"] += r["size"] or 0
        g["message_ids"].append(r["message_id"])
        g["parts"] += 1
    gtoks = [(g, archive._tokens(g["name"])) for g in groups.values()]
    cand = await _intro_posts(client, account, intro, max(1, min(int(posts or 30), 300)))
    if query:
        q = query.lower()
        cand = [p for p in cand if q in (p["text"] or "").lower()]
    pairs, unmatched = [], 0
    for p in cand[: int(posts or 30)]:
        text = p["text"] or ""
        info = archive.extract_info(text)
        ptok = archive._tokens(info.get("title", "") + " " + text[:200])
        scored = []
        for g, gt in gtoks:
            if not gt or not ptok:
                continue
            inter = len(ptok & gt)
            if not inter:
                continue
            sc = round(inter / min(len(ptok), len(gt)) * 0.7 + inter / len(ptok | gt) * 0.3, 3)
            if sc >= min_score:
                scored.append((sc, g))
        scored.sort(key=lambda x: -x[0])
        if not scored:
            unmatched += 1
            continue
        pairs.append({
            "post": {"message_id": p["message_id"], "title": info.get("title", ""), "link": readers.message_link(intro, p["message_id"]),
                     **{k: v for k, v in info.items() if k in ("passwords", "versions")}},
            "matches": [{"name": g["name"], "parts": g["parts"], "size": g["size"], "size_human": readers.human_size(g["size"]),
                         "message_ids": sorted(g["message_ids"])[:50], "score": sc,
                         "link": readers.message_link(files_ent, min(g["message_ids"]))} for sc, g in scored[: max(1, int(per_post or 3))]],
        })
    return {"intro_chat": readers.chat_brief(intro), "files_chat": readers.chat_brief(files_ent),
            "posts_checked": len(cand[: int(posts or 30)]), "matched": len(pairs), "unmatched": unmatched,
            "files_indexed": len(rows), "pairs": pairs,
            "hint": "Download a match with tg_download(chat=files_chat, message_ids=...). Low scores (<0.5) deserve a check or tg_ask_user."}
