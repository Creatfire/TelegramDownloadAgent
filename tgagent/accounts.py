"""Multiple accounts: stored configuration, Telethon client lifecycle, login by code/2FA or QR code."""
from __future__ import annotations

import asyncio
import io
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError,
    PasswordHashInvalidError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    SessionPasswordNeededError,
)
from telethon.tl import functions, types

from . import __version__
from .activity import bus
from .config import ACCOUNTS_FILE, SESSIONS_DIR, settings
from .i18n import L
from .secure import decrypt, encrypt, forget


class AccountError(Exception):
    pass


def proxy_to_telethon(proxy: dict | None) -> dict | None:
    if not proxy or not proxy.get("type") or not proxy.get("host"):
        return None
    p: dict[str, Any] = {"proxy_type": proxy["type"], "addr": proxy["host"], "port": int(proxy["port"]), "rdns": True}
    if proxy.get("username"):
        p["username"] = proxy["username"]
        p["password"] = proxy.get("password", "")
    return p


def qr_svg(data: str) -> str:
    import qrcode
    import qrcode.image.svg
    img = qrcode.make(data, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=2)
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue().decode("utf-8")


@dataclass
class Account:
    id: str
    name: str
    api_id: int
    api_hash_enc: str
    phone: str = ""
    # None follows the global default proxy; {"type": ""} means direct
    proxy: dict | None = None
    created: float = field(default_factory=time.time)

    # runtime
    client: TelegramClient | None = field(default=None, repr=False)
    status: str = "disconnected"  # disconnected/connecting/need_login/code_sent/password_needed/qr_waiting/ready/error
    error: str = ""
    me: dict | None = None
    phone_code_hash: str = ""
    qr: Any = field(default=None, repr=False)
    qr_task: asyncio.Task | None = field(default=None, repr=False)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    @property
    def api_hash(self) -> str:
        return decrypt(self.api_hash_enc)

    def effective_proxy(self) -> dict | None:
        return self.proxy if self.proxy is not None else settings.get("default_proxy")

    def to_store(self) -> dict:
        return {"id": self.id, "name": self.name, "api_id": self.api_id, "api_hash_enc": self.api_hash_enc,
                "phone": self.phone, "proxy": self.proxy, "created": self.created}

    def public(self) -> dict:
        phone = self.phone or ""
        masked = phone[:4] + "****" + phone[-3:] if len(phone) > 8 else phone
        return {"id": self.id, "name": self.name, "api_id": self.api_id, "phone": masked, "has_phone": bool(phone),
                "proxy": self.proxy, "effective_proxy": self.effective_proxy(), "status": self.status,
                "error": self.error, "me": self.me, "is_default": settings.get("default_account") == self.id}


class AccountManager:
    def __init__(self) -> None:
        self.accounts: dict[str, Account] = {}
        self._load()

    # ---------- persistence
    def _load(self) -> None:
        if not ACCOUNTS_FILE.exists():
            return
        known = Account.__dataclass_fields__
        for raw in json.loads(ACCOUNTS_FILE.read_text("utf-8")):
            acc = Account(**{k: v for k, v in raw.items() if k in known})
            self.accounts[acc.id] = acc

    def _save(self) -> None:
        ACCOUNTS_FILE.write_text(json.dumps([a.to_store() for a in self.accounts.values()], ensure_ascii=False, indent=2), "utf-8")

    def _session_path(self, acc_id: str) -> str:
        return str(SESSIONS_DIR / acc_id)

    # ---------- CRUD
    def list(self) -> list[dict]:
        return [a.public() for a in self.accounts.values()]

    def add(self, name: str, api_id: int, api_hash: str, phone: str = "", proxy: dict | None = None) -> Account:
        phone = re.sub(r"[^\d+]", "", phone or "")
        if phone and not phone.startswith("+"):
            phone = "+" + phone
        base = re.sub(r"[^a-zA-Z0-9_-]", "", (name or "").strip().replace(" ", "_")) or "account"
        acc_id, n = base.lower(), 1
        while acc_id in self.accounts:
            n += 1
            acc_id = f"{base.lower()}{n}"
        acc = Account(id=acc_id, name=(name or "").strip() or acc_id, api_id=int(api_id),
                      api_hash_enc=encrypt(api_hash.strip()), phone=phone, proxy=proxy)
        self.accounts[acc_id] = acc
        if not settings.get("default_account"):
            settings.update({"default_account": acc_id})
        self._save()
        bus.log("info", "system", L(f"添加账号 {acc.name}", f"Account added: {acc.name}"), f"api_id={acc.api_id}")
        return acc

    async def update(self, acc_id: str, values: dict) -> Account:
        acc = self.get(acc_id)
        reconnect = False
        if values.get("name"):
            acc.name = values["name"]
        if values.get("api_id"):
            acc.api_id = int(values["api_id"]); reconnect = True
        if values.get("api_hash"):
            forget(acc.api_hash_enc)
            acc.api_hash_enc = encrypt(values["api_hash"].strip()); reconnect = True
        if "phone" in values and values["phone"] is not None:
            phone = re.sub(r"[^\d+]", "", values["phone"])
            acc.phone = ("+" + phone.lstrip("+")) if phone else ""
        if "proxy" in values:
            acc.proxy = values["proxy"]; reconnect = True
        self._save()
        if reconnect and acc.client:
            await self.disconnect(acc_id)
            asyncio.create_task(self.connect(acc_id))
        return acc

    async def remove(self, acc_id: str, logout: bool = False) -> None:
        acc = self.get(acc_id)
        if logout and acc.client and acc.status == "ready":
            try:
                await acc.client.log_out()
            except Exception:
                pass
        await self.disconnect(acc_id)
        self.accounts.pop(acc_id, None)
        forget(acc.api_hash_enc)
        for suffix in (".session", ".session-journal"):
            p = SESSIONS_DIR / f"{acc_id}{suffix}"
            if p.exists():
                p.unlink()
        if settings.get("default_account") == acc_id:
            settings.update({"default_account": next(iter(self.accounts), "")})
        self._save()
        bus.log("warn", "system", L(f"移除账号 {acc.name}", f"Account removed: {acc.name}"),
                L("已同时注销 Telegram 会话", "Telegram session logged out") if logout else L("仅删除本地会话", "Local session deleted"))

    def get(self, acc_id: str | None) -> Account:
        if not acc_id:
            acc_id = settings.get("default_account") or next(
                (a.id for a in self.accounts.values() if a.status == "ready"), None)
            if not acc_id and self.accounts:
                acc_id = next(iter(self.accounts))
        if not acc_id or acc_id not in self.accounts:
            raise AccountError(L(f"账号不存在: {acc_id!r}。可用账号: {list(self.accounts) or '无（请先在控制台添加）'}",
                                 f"No such account: {acc_id!r}. Available: {list(self.accounts) or 'none (add one in the console)'}"))
        return self.accounts[acc_id]

    async def client(self, acc_id: str | None = None) -> tuple[Account, TelegramClient]:
        """A logged-in client, or an error that tells the agent what the user has to do."""
        acc = self.get(acc_id)
        if acc.status != "ready" or not acc.client:
            if acc.status in ("disconnected", "error"):
                await self.connect(acc.id)
            if acc.status != "ready":
                hint = L("请让用户在 Web 控制台的“账号”页完成登录。", "Ask the user to log in on the console's Accounts page.")
                raise AccountError(L(f"账号 {acc.id} 当前状态为 {acc.status}，不可用。", f"Account {acc.id} is {acc.status}. ")
                                   + (hint if acc.status in ("need_login", "code_sent", "password_needed", "qr_waiting") else acc.error))
        return acc, acc.client

    # ---------- connection and login
    def _make_client(self, acc: Account) -> TelegramClient:
        return TelegramClient(
            self._session_path(acc.id), acc.api_id, acc.api_hash,
            proxy=proxy_to_telethon(acc.effective_proxy()),
            device_model="TG Agent", system_version="Desktop", app_version=__version__,
            flood_sleep_threshold=60, receive_updates=False, connection_retries=3, retry_delay=2,
        )

    async def connect(self, acc_id: str) -> Account:
        acc = self.get(acc_id)
        async with acc.lock:
            if acc.client and acc.client.is_connected() and acc.status == "ready":
                return acc
            acc.status, acc.error = "connecting", ""
            try:
                if not acc.client:
                    acc.client = self._make_client(acc)
                if not acc.client.is_connected():
                    await asyncio.wait_for(acc.client.connect(), timeout=40)
                if await acc.client.is_user_authorized():
                    await self._on_authorized(acc)
                else:
                    acc.status = "need_login"
            except Exception as e:
                acc.status, acc.error = "error", f"{type(e).__name__}: {e}"
                bus.log("error", "system", L(f"账号 {acc.name} 连接失败", f"Account {acc.name} failed to connect"), acc.error)
        return acc

    async def _on_authorized(self, acc: Account) -> None:
        me = await acc.client.get_me()
        acc.me = {"id": me.id, "username": me.username, "name": " ".join(x for x in (me.first_name, me.last_name) if x),
                  "premium": bool(getattr(me, "premium", False))}
        if not acc.phone and getattr(me, "phone", None):
            acc.phone = "+" + me.phone
            self._save()
        acc.status, acc.error, acc.phone_code_hash = "ready", "", ""
        bus.log("success", "system", L(f"账号 {acc.name} 已就绪", f"Account {acc.name} ready"), f"@{me.username or me.id}")

    async def disconnect(self, acc_id: str) -> None:
        acc = self.get(acc_id)
        self._stop_qr(acc)
        if acc.client:
            try:
                await acc.client.disconnect()
            except Exception:
                pass
        acc.client, acc.status = None, "disconnected"

    async def _ready_for_login(self, acc_id: str) -> Account:
        acc = await self.connect(acc_id)
        if acc.status != "ready" and (not acc.client or not acc.client.is_connected()):
            raise AccountError(acc.error or L("无法连接 Telegram，请检查代理设置", "Cannot reach Telegram; check the proxy settings"))
        return acc

    async def send_code(self, acc_id: str) -> Account:
        acc = await self._ready_for_login(acc_id)
        if acc.status == "ready":
            return acc
        if not acc.phone:
            raise AccountError(L("此账号没有手机号，请编辑账号填写手机号，或使用扫码登录", "No phone number on this account: add one or use QR login"))
        self._stop_qr(acc)
        try:
            sent = await acc.client.send_code_request(acc.phone)
        except FloodWaitError as e:
            raise AccountError(L(f"请求过于频繁，需等待 {e.seconds} 秒后再发送验证码", f"Too many requests; wait {e.seconds}s before sending a code"))
        acc.phone_code_hash = sent.phone_code_hash
        acc.status = "code_sent"
        bus.log("info", "system", L(f"已向 {acc.name} 发送登录验证码", f"Login code sent for {acc.name}"),
                L("请查看 Telegram 客户端或短信", "Check your Telegram app or SMS"))
        return acc

    async def submit_code(self, acc_id: str, code: str) -> Account:
        acc = self.get(acc_id)
        if acc.status != "code_sent" or not acc.client:
            raise AccountError(L("请先发送验证码", "Send a code first"))
        try:
            await acc.client.sign_in(acc.phone, code=code.strip(), phone_code_hash=acc.phone_code_hash)
        except SessionPasswordNeededError:
            acc.status = "password_needed"
            return acc
        except PhoneCodeInvalidError:
            raise AccountError(L("验证码错误", "Wrong code"))
        except PhoneCodeExpiredError:
            acc.status = "need_login"
            raise AccountError(L("验证码已过期，请重新发送", "Code expired; send a new one"))
        await self._on_authorized(acc)
        return acc

    async def submit_password(self, acc_id: str, password: str) -> Account:
        acc = self.get(acc_id)
        if acc.status != "password_needed" or not acc.client:
            raise AccountError(L("当前不需要两步验证密码", "No 2FA password is needed right now"))
        try:
            await acc.client.sign_in(password=password)
        except PasswordHashInvalidError:
            raise AccountError(L("两步验证密码错误", "Wrong 2FA password"))
        await self._on_authorized(acc)
        return acc

    # ---------- QR login
    def _stop_qr(self, acc: Account) -> None:
        if acc.qr_task and not acc.qr_task.done():
            acc.qr_task.cancel()
        acc.qr_task, acc.qr = None, None
        if acc.client:
            acc.client._no_updates = True

    async def qr_start(self, acc_id: str) -> dict:
        """Return a fresh QR code (SVG) and keep waiting for it to be scanned in the background."""
        acc = await self._ready_for_login(acc_id)
        if acc.status == "ready":
            return {"status": "ready"}
        client = acc.client
        # The QR flow is completed by an UpdateLoginToken push, so let this connection receive updates
        client._no_updates = False
        if acc.qr is None:
            acc.qr = await client.qr_login()
        else:
            await self._qr_refresh(acc)
            if acc.status == "ready":
                return {"status": "ready"}
        acc.status = "qr_waiting"
        if not acc.qr_task or acc.qr_task.done():
            acc.qr_task = asyncio.create_task(self._qr_wait(acc))
        return {"status": acc.status, "url": acc.qr.url, "expires": acc.qr.expires.timestamp(), "svg": qr_svg(acc.qr.url)}

    async def _qr_refresh(self, acc: Account) -> None:
        """Request a new token; if the previous one was already scanned this completes the login."""
        resp = await acc.client(acc.qr._request)
        if isinstance(resp, types.auth.LoginTokenMigrateTo):
            await acc.client._switch_dc(resp.dc_id)
            resp = await acc.client(functions.auth.ImportLoginTokenRequest(resp.token))
        if isinstance(resp, types.auth.LoginTokenSuccess):
            await acc.client._on_login(resp.authorization.user)
            self._stop_qr(acc)
            await self._on_authorized(acc)
        else:
            acc.qr._resp = resp

    async def _qr_wait(self, acc: Account) -> None:
        try:
            while acc.status == "qr_waiting" and acc.qr:
                try:
                    await acc.qr.wait()
                    self._stop_qr(acc)
                    await self._on_authorized(acc)
                    return
                except asyncio.TimeoutError:
                    await self._qr_refresh(acc)   # catches a scan whose update was missed
                except SessionPasswordNeededError:
                    acc.client._no_updates = True
                    acc.status = "password_needed"
                    return
        except asyncio.CancelledError:
            raise
        except SessionPasswordNeededError:
            acc.status = "password_needed"
        except Exception as e:
            acc.status, acc.error = "need_login", f"{type(e).__name__}: {e}"

    async def connect_all(self) -> None:
        await asyncio.gather(*(self.connect(a) for a in list(self.accounts)), return_exceptions=True)

    async def shutdown(self) -> None:
        for acc_id in list(self.accounts):
            await self.disconnect(acc_id)


manager = AccountManager()
