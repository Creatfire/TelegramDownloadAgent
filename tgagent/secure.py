"""Protect secrets at rest.

Windows: DPAPI (only the current Windows user can decrypt).
macOS / Linux: the system keychain via `keyring`; if no keychain is available the value is stored
base64-encoded (obfuscated only) and a warning is shown in the console.
"""
from __future__ import annotations

import base64
import sys
import uuid

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    class _Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    _crypt32 = ctypes.windll.crypt32
    _kernel32 = ctypes.windll.kernel32

    def _to_blob(data: bytes) -> _Blob:
        buf = ctypes.create_string_buffer(data, len(data))
        return _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))

    def _from_blob(blob: _Blob) -> bytes:
        try:
            return ctypes.string_at(blob.pbData, blob.cbData)
        finally:
            _kernel32.LocalFree(blob.pbData)

    def _protect(data: bytes) -> bytes:
        out = _Blob()
        if not _crypt32.CryptProtectData(ctypes.byref(_to_blob(data)), "tgagent", None, None, None, 0, ctypes.byref(out)):
            raise OSError("CryptProtectData failed")
        return _from_blob(out)

    def _unprotect(data: bytes) -> bytes:
        out = _Blob()
        if not _crypt32.CryptUnprotectData(ctypes.byref(_to_blob(data)), None, None, None, None, 0, ctypes.byref(out)):
            raise OSError("CryptUnprotectData failed")
        return _from_blob(out)

KEYRING_SERVICE = "tg-agent"
WEAK_STORAGE = False   # True when secrets could only be obfuscated


def encrypt(text: str) -> str:
    global WEAK_STORAGE
    if sys.platform == "win32":
        return "dpapi:" + base64.b64encode(_protect(text.encode("utf-8"))).decode("ascii")
    try:
        import keyring
        name = uuid.uuid4().hex
        keyring.set_password(KEYRING_SERVICE, name, text)
        return "keyring:" + name
    except Exception:
        WEAK_STORAGE = True
        return "b64:" + base64.b64encode(text.encode("utf-8")).decode("ascii")


def decrypt(value: str) -> str:
    if not value:
        return ""
    if value.startswith("dpapi:"):
        return _unprotect(base64.b64decode(value[6:])).decode("utf-8")
    if value.startswith("keyring:"):
        import keyring
        return keyring.get_password(KEYRING_SERVICE, value[8:]) or ""
    if value.startswith("b64:"):
        return base64.b64decode(value[4:]).decode("utf-8")
    return value


def forget(value: str) -> None:
    if value and value.startswith("keyring:"):
        try:
            import keyring
            keyring.delete_password(KEYRING_SERVICE, value[8:])
        except Exception:
            pass
