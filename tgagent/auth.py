"""Local access token. Every API / MCP request must carry it, so other programs on this
machine cannot use the Telegram account through the service."""
from __future__ import annotations

import os
import secrets

from .config import TOKEN_FILE

COOKIE = "tga_token"


def get_token() -> str:
    if TOKEN_FILE.exists():
        tok = TOKEN_FILE.read_text("utf-8").strip()
        if tok:
            return tok
    return regenerate()


def regenerate() -> str:
    tok = secrets.token_urlsafe(24)
    TOKEN_FILE.write_text(tok, "utf-8")
    try:
        os.chmod(TOKEN_FILE, 0o600)
    except OSError:
        pass
    return tok


def check(value: str | None) -> bool:
    return bool(value) and secrets.compare_digest(value, get_token())
