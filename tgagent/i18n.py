"""Minimal bilingual helper for server-side, user-facing text."""
from __future__ import annotations

from .config import settings


def lang() -> str:
    return "zh" if settings.get("language") == "zh" else "en"


def L(zh: str, en: str) -> str:
    """Pick the string for the configured language."""
    return zh if lang() == "zh" else en
