"""Read-only queries: resolve chats/links, dialogs, messages, search, file listings."""
from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from telethon import TelegramClient, utils
from telethon.tl import functions, types

from . import archive, index
from .db import db as _db
from .config import settings

# ---------------------------------------------------------------- link parsing

_LINK_RE = re.compile(r"^(?:https?://)?(?:www\.)?(?:t|telegram)\.(?:me|dog)/(.+)$", re.I)


class ChatRef:
    def __init__(self, chat: Any = None, msg_id: int | None = None, invite: str | None = None):
        self.chat, self.msg_id, self.invite = chat, msg_id, invite


def parse_ref(ref: Any) -> ChatRef:
    """Accepts 123 / -100123 / @name / name / t.me/name[/msg] / t.me/c/123/msg / t.me/s/name / t.me/+hash / tg://resolve."""
    if isinstance(ref, int):
        return ChatRef(ref)
    s = str(ref).strip()
    if re.fullmatch(r"-?\d+", s):
        return ChatRef(int(s))
    m = re.match(r"^tg://resolve\?domain=([\w]+)(?:&post=(\d+))?", s)
    if m:
        return ChatRef(m.group(1), int(m.group(2)) if m.group(2) else None)
    m = _LINK_RE.match(s)
    if m:
        path = m.group(1).split("?")[0].strip("/")
        parts = path.split("/")
        if parts[0].startswith("+") or parts[0] == "joinchat":
            return ChatRef(invite=parts[0][1:] if parts[0].startswith("+") else parts[1])
        if parts[0] == "s" and len(parts) > 1:
            parts = parts[1:]
        if parts[0] == "c" and len(parts) >= 2:
            chat = int("-100" + parts[1])
            msg = int(parts[-1]) if len(parts) >= 3 and parts[-1].isdigit() else None
            return ChatRef(chat, msg)
        msg = int(parts[-1]) if len(parts) >= 2 and parts[-1].isdigit() else None
        return ChatRef(parts[0], msg)
    return ChatRef(s.lstrip("@"))


async def get_entity(client: TelegramClient, ref: Any):
    cr = parse_ref(ref)
    if cr.invite:
        raise ValueError("This is an invite link: inspect it with tg_resolve_chat. TG Agent never joins chats.")
    return await _entity(client, cr.chat)


# Entity cache: Telegram rate-limits ResolveUsername hard, and get_entity(username) always sends one
_ENTITY_TTL = 1800
_entity_cache: dict[tuple[int, Any], tuple[float, Any]] = {}


def _cache_key(client: TelegramClient, chat: Any) -> tuple[int, Any]:
    return id(client), chat.lower() if isinstance(chat, str) else chat


def remember(client: TelegramClient, entity) -> None:
    now = time.time()
    _entity_cache[_cache_key(client, utils.get_peer_id(entity))] = (now, entity)
    if getattr(entity, "username", None):
        _entity_cache[_cache_key(client, entity.username)] = (now, entity)


async def _entity(client: TelegramClient, chat: Any):
    key = _cache_key(client, chat)
    hit = _entity_cache.get(key)
    if hit and time.time() - hit[0] < _ENTITY_TTL:
        return hit[1]
    try:
        entity = None
        if isinstance(chat, str):
            # The session file remembers usernames it has seen; resolving through it avoids
            # ResolveUsername, which Telegram rate-limits heavily (and survives restarts).
            try:
                entity = await client.get_entity(client.session.get_input_entity(chat))
            except (ValueError, KeyError, TypeError):
                entity = None
        if entity is None:
            entity = await client.get_entity(chat)
    except ValueError:
        if not isinstance(chat, int):
            raise
        # private channels only get an access_hash through the dialog list
        async for _ in client.iter_dialogs():
            pass
        entity = await client.get_entity(chat)
    remember(client, entity)
    _entity_cache[key] = (time.time(), entity)
    return entity


# ---------------------------------------------------------------- serialization

def iso(dt: datetime | None) -> str | None:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None


def parse_date(s: str | None) -> datetime | None:
    if not s:
        return None
    s = s.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(s) if "T" in s or "-" in s else None
    if dt and dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def chat_type(entity) -> str:
    if isinstance(entity, types.User):
        return "bot" if entity.bot else "user"
    if isinstance(entity, types.Channel):
        return "channel" if entity.broadcast else "supergroup"
    if isinstance(entity, (types.Chat, types.ChatForbidden)):
        return "group"
    return "unknown"


def chat_title(entity) -> str:
    return utils.get_display_name(entity) or str(getattr(entity, "id", ""))


def entity_username(entity) -> str | None:
    """Public username; newer chats keep it in `usernames` (collectible / multiple usernames) instead."""
    if getattr(entity, "username", None):
        return entity.username
    for u in getattr(entity, "usernames", None) or []:
        if getattr(u, "active", False):
            return u.username
    return None


def chat_brief(entity) -> dict:
    return {
        "id": utils.get_peer_id(entity),
        "title": chat_title(entity),
        "username": entity_username(entity),
        "type": chat_type(entity),
    }


def message_link(entity, msg_id: int) -> str | None:
    username = entity_username(entity)
    if username:
        return f"https://t.me/{username}/{msg_id}"
    if isinstance(entity, types.Channel):
        return f"https://t.me/c/{entity.id}/{msg_id}"
    return None


def media_kind(msg) -> str | None:
    if msg.photo:
        return "photo"
    if msg.sticker:
        return "sticker"
    if msg.gif:
        return "gif"
    if msg.video_note:
        return "round"
    if msg.video:
        return "video"
    if msg.voice:
        return "voice"
    if msg.audio:
        return "audio"
    if msg.document:
        return "document"
    return None


def file_info(msg) -> dict | None:
    kind = media_kind(msg)
    if not kind:
        return None
    f = msg.file
    name = f.name
    if not name:
        ext = f.ext or ""
        name = f"{kind}_{msg.id}{ext}"
    info = {"kind": kind, "name": name, "size": f.size or 0, "mime": f.mime_type, "ext": (f.ext or "").lstrip(".")}
    if f.duration:
        info["duration"] = int(f.duration)
    if f.width and f.height:
        info["resolution"] = f"{f.width}x{f.height}"
    arc = split_info(name)
    if arc:
        info["archive"] = arc
    return info


# ---------------------------------------------------------------- split archives
_SPLIT_PATTERNS = [
    re.compile(r"^(?P<base>.+\.(?:7z|zip|rar|tar|gz|tgz|bz2|xz|iso|bin))\.(?P<part>\d{2,4})$", re.I),   # x.7z.001
    re.compile(r"^(?P<stem>.+)\.part(?P<part>\d{1,4})\.(?P<ext>rar|exe)$", re.I),                     # x.part1.rar
    re.compile(r"^(?P<stem>.+)\.z(?P<part>\d{2})$", re.I),                                            # x.z01 (+ x.zip)
    re.compile(r"^(?P<base>.+)\.(?P<part>\d{3})$"),                                                   # x.001
]


def split_info(name: str) -> dict | None:
    """Detect volumes of a split archive. Returns {"set": <name of the whole archive>, "part": n} or None."""
    for i, rx in enumerate(_SPLIT_PATTERNS):
        m = rx.match(name or "")
        if not m:
            continue
        part = int(m.group("part"))
        if i == 1:
            return {"set": f"{m.group('stem')}.{m.group('ext').lower()}", "part": part}
        if i == 2:
            return {"set": f"{m.group('stem')}.zip", "part": part}
        return {"set": m.group("base"), "part": part}
    return None


def archive_sets(files: list[dict]) -> list[dict]:
    """Group file rows (with an "archive" field) into sets and report missing volumes."""
    sets: dict[str, dict] = {}
    for f in files:
        a = f.get("archive")
        if not a:
            continue
        g = sets.setdefault(a["set"], {"set": a["set"], "parts": [], "size": 0, "message_ids": []})
        g["parts"].append(a["part"])
        g["size"] += f.get("size", 0)
        g["message_ids"].append(f.get("message_id"))
    out = []
    for g in sets.values():
        parts = sorted(set(g["parts"]))
        first = 0 if 0 in parts else 1
        g["parts"] = parts
        g["count"] = len(parts)
        g["missing"] = [n for n in range(first, parts[-1] + 1) if n not in parts][:50]
        g["size_human"] = human_size(g["size"])
        out.append(g)
    return sorted(out, key=lambda g: g["set"].lower())


def sender_brief(msg) -> dict | None:
    s = msg.sender
    if s is None:
        return {"name": msg.post_author} if getattr(msg, "post_author", None) else None
    return {"id": s.id, "name": utils.get_display_name(s), "username": getattr(s, "username", None)}


def message_dict(msg, entity, text_max: int | None = 500) -> dict:
    text = msg.message or ""
    truncated = text_max is not None and len(text) > text_max
    d: dict[str, Any] = {
        "id": msg.id,
        "date": iso(msg.date),
        "text": text[:text_max] + "…" if truncated else text,
    }
    if truncated:
        d["text_truncated"] = True
    sb = sender_brief(msg)
    if sb:
        d["sender"] = sb
    fi = file_info(msg)
    if fi:
        d["file"] = fi
    if msg.views is not None:
        d["views"] = msg.views
    if msg.reply_to and getattr(msg.reply_to, "reply_to_msg_id", None):
        d["reply_to"] = msg.reply_to.reply_to_msg_id
    if msg.grouped_id:
        d["album"] = msg.grouped_id
    if msg.fwd_from:
        d["forwarded"] = True
    link = message_link(entity, msg.id)
    if link:
        d["link"] = link
    return d


def human_size(n: float) -> str:
    if not n or n < 1024:
        return "0 KB"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.2f} {unit}"
        n /= 1024
    return str(n)


# ---------------------------------------------------------------- queries

async def list_dialogs(client: TelegramClient, kind: str = "all", query: str = "", limit: int = 100) -> dict:
    limit = max(1, min(int(limit or 100), 500))
    q = (query or "").lower()
    out = []
    async for d in client.iter_dialogs():
        t = chat_type(d.entity)
        if kind and kind != "all":
            want = {"channels": ("channel",), "groups": ("group", "supergroup"), "users": ("user", "bot")}.get(kind, (kind,))
            if t not in want:
                continue
        remember(client, d.entity)
        b = chat_brief(d.entity)
        if q and q not in (b["title"] or "").lower() and q not in (b["username"] or "").lower():
            continue
        b["unread"] = d.unread_count
        b["last_message_date"] = iso(d.date)
        pc = getattr(d.entity, "participants_count", None)
        if pc:
            b["members"] = pc
        out.append(b)
        if len(out) >= limit:
            break
    return {"count": len(out), "dialogs": out}


async def resolve_chat(client: TelegramClient, ref: str) -> dict:
    cr = parse_ref(ref)
    if cr.invite:
        res = await client(functions.messages.CheckChatInviteRequest(cr.invite))
        if isinstance(res, (types.ChatInviteAlready, types.ChatInvitePeek)):
            return {"joined": True, **(await _chat_info(client, res.chat))}
        return {
            "joined": False, "invite": True, "title": res.title, "about": getattr(res, "about", None),
            "members": res.participants_count, "type": "channel" if res.broadcast else "group",
            "note": "Not joined. TG Agent is read-only and never joins; the user must join in Telegram first.",
        }
    entity = await _entity(client, cr.chat)
    info = await _chat_info(client, entity)
    if cr.msg_id:
        info["message_id"] = cr.msg_id
    return info


async def _chat_info(client: TelegramClient, entity) -> dict:
    info = chat_brief(entity)
    try:
        if isinstance(entity, types.Channel):
            full = await client(functions.channels.GetFullChannelRequest(entity))
            info["about"] = full.full_chat.about
            info["members"] = full.full_chat.participants_count
            info["joined"] = not entity.left
        elif isinstance(entity, types.Chat):
            full = await client(functions.messages.GetFullChatRequest(entity.id))
            info["about"] = full.full_chat.about
            info["members"] = entity.participants_count
        elif isinstance(entity, types.User):
            full = await client(functions.users.GetFullUserRequest(entity))
            info["about"] = full.full_user.about
    except Exception as e:  # e.g. no permission: still return the basics
        info["info_error"] = str(e)
    info["public"] = bool(info.get("username"))
    if info["username"]:
        info["link"] = f"https://t.me/{info['username']}"
    async for m in client.iter_messages(entity, limit=1):
        info["latest_message_id"] = m.id
        info["latest_message_date"] = iso(m.date)
    return info


async def get_messages(client: TelegramClient, chat: str, limit: int = 30, offset_id: int = 0,
                       min_id: int = 0, max_id: int = 0, since: str | None = None, until: str | None = None,
                       query: str = "", media_only: bool = False, oldest_first: bool = False,
                       text_max: int = 500) -> dict:
    entity = await get_entity(client, chat)
    limit = max(1, min(int(limit or 30), 200))
    since_dt, until_dt = parse_date(since), parse_date(until)
    kwargs: dict[str, Any] = dict(limit=None, wait_time=settings.get("read_wait_time"),
                                  reverse=oldest_first, search=query or None)
    if offset_id:
        kwargs["offset_id"] = offset_id
    if min_id:
        kwargs["min_id"] = min_id
    if max_id:
        kwargs["max_id"] = max_id
    if oldest_first and since_dt:
        kwargs["offset_date"] = since_dt
    elif not oldest_first and until_dt:
        kwargs["offset_date"] = until_dt
    out, last_id, scanned = [], None, 0
    acc_id = account_of(client)
    chat_id = utils.get_peer_id(entity)
    async for msg in client.iter_messages(entity, **kwargs):
        if acc_id and not isinstance(msg, types.MessageService):
            archive.add(acc_id, chat_id, msg)
        scanned += 1
        last_id = msg.id
        if since_dt and not oldest_first and msg.date < since_dt:
            last_id = None
            break
        if until_dt and oldest_first and msg.date > until_dt:
            last_id = None
            break
        if isinstance(msg, types.MessageService):
            continue
        if media_only and not media_kind(msg):
            if scanned >= limit * 20:
                break
            continue
        out.append(message_dict(msg, entity, text_max))
        if len(out) >= limit:
            break
    else:
        last_id = None
    archive.flush()
    return {
        "chat": chat_brief(entity), "count": len(out), "messages": out,
        "next_offset_id": last_id,
        "hint": "Pass offset_id=next_offset_id for the next page" if last_id else "End of history",
    }


async def search_messages(client: TelegramClient, query: str, chat: str | None = None, limit: int = 30,
                          text_max: int = 300) -> dict:
    limit = max(1, min(int(limit or 30), 100))
    if chat:
        return await get_messages(client, chat, limit=limit, query=query, text_max=text_max)
    out = []
    acc_id = account_of(client)
    async for msg in client.iter_messages(None, search=query, limit=limit, wait_time=settings.get("read_wait_time")):
        ent = msg.chat
        if acc_id and ent is not None:
            archive.add(acc_id, utils.get_peer_id(ent), msg)
        d = message_dict(msg, ent, text_max)
        d["chat"] = chat_brief(ent) if ent else {"id": msg.chat_id}
        out.append(d)
    archive.flush()
    return {"query": query, "scope": "global (joined chats)", "count": len(out), "messages": out}


async def get_message(client: TelegramClient, link: str | None = None, chat: str | None = None,
                      message_id: int | None = None) -> dict:
    if link:
        cr = parse_ref(link)
        if not cr.msg_id:
            raise ValueError("The link has no message id, e.g. https://t.me/name/123")
        chat, message_id = cr.chat, cr.msg_id
        entity = await _entity(client, chat)
    else:
        if not chat or not message_id:
            raise ValueError("Provide link, or chat + message_id")
        entity = await get_entity(client, chat)
    msg = await client.get_messages(entity, ids=int(message_id))
    if msg and account_of(client):
        archive.add(account_of(client), utils.get_peer_id(entity), msg)
        archive.flush()
    if not msg:
        raise ValueError(f"Message {message_id} does not exist or is not accessible")
    d = message_dict(msg, entity, text_max=None)
    d["chat"] = chat_brief(entity)
    if msg.grouped_id:  # album: include the other items
        around = await client.get_messages(entity, ids=list(range(msg.id - 10, msg.id + 11)))
        d["album_items"] = [message_dict(m, entity, 200) for m in around
                            if m and m.grouped_id == msg.grouped_id and m.id != msg.id]
    return d


# ---------------------------------------------------------------- file listing

_TYPE_FILTERS = {
    "document": types.InputMessagesFilterDocument,
    "video": types.InputMessagesFilterVideo,
    "photo": types.InputMessagesFilterPhotos,
    "audio": types.InputMessagesFilterMusic,
    "voice": types.InputMessagesFilterVoice,
    "round": types.InputMessagesFilterRoundVideo,
    "gif": types.InputMessagesFilterGif,
}
ALL_FILE_TYPES = ["document", "video", "audio", "photo", "voice", "gif", "round"]


class FileFilter:
    def __init__(self, types_: list[str] | None = None, name_contains: str = "", extensions: list[str] | None = None,
                 min_size_mb: float | None = None, max_size_mb: float | None = None,
                 since: str | None = None, until: str | None = None):
        self.types = [t for t in (types_ or ALL_FILE_TYPES) if t in ALL_FILE_TYPES + ["sticker"]] or ALL_FILE_TYPES
        self.name = (name_contains or "").lower()
        self.exts = {e.lower().lstrip(".") for e in (extensions or []) if e}
        self.min = int(min_size_mb * 1024 * 1024) if min_size_mb else None
        self.max = int(max_size_mb * 1024 * 1024) if max_size_mb else None
        self.since, self.until = parse_date(since), parse_date(until)

    def tg_filter(self):
        # Let the server filter for a single kind only: Telegram's Document filter also matches videos/audio
        return _TYPE_FILTERS[self.types[0]]() if len(self.types) == 1 and self.types[0] in _TYPE_FILTERS else None

    def match(self, msg) -> dict | None:
        fi = file_info(msg)
        if not fi or fi["kind"] not in self.types:
            return None
        if self.name and self.name not in fi["name"].lower() and self.name not in (msg.message or "").lower():
            return None
        if self.exts and fi["ext"].lower() not in self.exts:
            return None
        if self.min is not None and fi["size"] < self.min:
            return None
        if self.max is not None and fi["size"] > self.max:
            return None
        return fi


async def iter_files(client: TelegramClient, entity, flt: FileFilter, offset_id: int = 0,
                     oldest_first: bool = False, scan_limit: int | None = None,
                     min_id: int = 0) -> AsyncIterator[tuple[Any, dict | None]]:
    """Yield (msg, file_info|None); None means scanned but not matching (still advances the cursor)."""
    kwargs: dict[str, Any] = dict(limit=scan_limit, wait_time=settings.get("read_wait_time"),
                                  reverse=oldest_first, filter=flt.tg_filter())
    if offset_id:
        kwargs["offset_id"] = offset_id
    if oldest_first and flt.since:
        kwargs["offset_date"] = flt.since
    elif not oldest_first and flt.until:
        kwargs["offset_date"] = flt.until
    if min_id:
        kwargs["min_id"] = min_id
    acc_id = account_of(client)
    chat_id_ = utils.get_peer_id(entity)
    try:
        async for msg in client.iter_messages(entity, **kwargs):
            if not oldest_first and flt.since and msg.date < flt.since:
                return
            if oldest_first and flt.until and msg.date > flt.until:
                return
            if acc_id:
                if not isinstance(msg, types.MessageService):
                    archive.add(acc_id, chat_id_, msg)
                fi_any = file_info(msg)
                if fi_any:
                    index.add(acc_id, entity, msg, fi_any)
            yield msg, flt.match(msg)
    finally:
        index.flush()
        archive.flush()


def account_of(client: TelegramClient) -> str | None:
    from .accounts import manager
    return next((a.id for a in manager.accounts.values() if a.client is client), None)


def file_row(msg, entity, fi: dict) -> dict:
    row = {"message_id": msg.id, "date": iso(msg.date), **fi}
    link = message_link(entity, msg.id)
    if link:
        row["link"] = link
    if msg.message:
        row["caption"] = msg.message[:120]
    return row


async def list_files(client: TelegramClient, chat: str, limit: int = 100, offset_id: int = 0,
                     oldest_first: bool = False, scan_limit: int = 5000, **filters) -> dict:
    entity = await get_entity(client, chat)
    limit = max(1, min(int(limit or 100), 1000))
    flt = FileFilter(**filters)
    files, total, by_kind = [], 0, {}
    scanned, last_id, exhausted = 0, None, True
    async for msg, fi in iter_files(client, entity, flt, offset_id, oldest_first, scan_limit=int(scan_limit or 5000)):
        scanned += 1
        last_id = msg.id
        if fi:
            row = file_row(msg, entity, fi)
            fid = getattr(msg.document or msg.photo, "id", None)
            if fid and _db.one("SELECT 1 FROM downloads WHERE file_id=?", (fid,)):
                row["downloaded"] = True
            files.append(row)
            total += fi["size"]
            by_kind[fi["kind"]] = by_kind.get(fi["kind"], 0) + 1
            if len(files) >= limit:
                exhausted = False
                break
    else:
        exhausted = scanned < int(scan_limit or 5000)
    return {
        "chat": chat_brief(entity),
        "count": len(files), "total_size": total, "total_size_human": human_size(total), "by_kind": by_kind,
        "archive_sets": [{k: v for k, v in g.items() if k != "message_ids"} for g in archive_sets(files)],
        "scanned_messages": scanned,
        "next_offset_id": None if exhausted else last_id,
        "hint": ("Scanned to the end" if exhausted else
                 "More available: pass offset_id=next_offset_id. For a complete list use tg_index_chat or tg_export."),
        "files": files,
    }
