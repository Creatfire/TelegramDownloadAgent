"""After-download processing with 7-Zip: test or extract archives (split sets start from their first volume)."""
from __future__ import annotations

import asyncio
import os
import re
import shutil
from pathlib import Path

from .config import settings
from .i18n import L
from .readers import split_info


def sevenzip() -> str | None:
    cand = [settings.get("sevenzip_path") or "", shutil.which("7z") or "", shutil.which("7za") or "",
            r"C:\Program Files\7-Zip\7z.exe", r"C:\Program Files (x86)\7-Zip\7z.exe", "/usr/bin/7z", "/opt/homebrew/bin/7z"]
    return next((c for c in cand if c and Path(c).exists()), None)


def first_volume(path: Path) -> Path:
    """For x.7z.003 / x.part3.rar return the first volume next to it (if present)."""
    info = split_info(path.name)
    if not info:
        return path
    for cand in (path.with_name(re.sub(r"\.\d{2,4}$", lambda m: "." + "1".zfill(len(m.group(0)) - 1), path.name)),
                 path.with_name(re.sub(r"\.part\d+\.", lambda m: ".part" + "1".zfill(len(m.group(0)) - 6) + ".", path.name, flags=re.I))):
        if cand.exists():
            return cand
    return path


def inside_downloads(p: Path) -> bool:
    root = Path(settings.get("download_dir")).resolve()
    p = p.resolve()
    return p == root or root in p.parents


async def run_7z(archive: Path, password: str | None, test_only: bool, on_progress) -> tuple[bool, str, Path | None]:
    exe = sevenzip()
    if not exe:
        return False, L("未找到 7-Zip，请安装 7-Zip 或在设置中填写 7z 路径", "7-Zip not found: install it or set its path in Settings"), None
    info = split_info(archive.name)
    base = (info["set"] if info else archive.name)
    base = re.sub(r"\.(7z|zip|rar|tar|gz|tgz|bz2|xz)$", "", base, flags=re.I)
    dest = archive.parent / base
    args = [exe, "t" if test_only else "x", str(archive), "-y", "-bsp1", "-bso0",
            f"-p{password or ''}"]
    if not test_only:
        args.append(f"-o{dest}")
    proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                                                creationflags=getattr(__import__("subprocess"), "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0)
    tail = ""
    buf = b""
    while True:
        chunk = await proc.stdout.read(256)
        if not chunk:
            break
        buf += chunk
        text = buf.decode("utf-8", "ignore")
        for m in re.finditer(r"(\d{1,3})%", text):
            on_progress(int(m.group(1)))
        tail = (tail + text)[-2000:]
        buf = b""
    code = await proc.wait()
    if code == 0:
        return True, L("完成", "OK"), (None if test_only else dest)
    low = tail.lower()
    if "wrong password" in low or "data error in encrypted" in low or "cannot open encrypted" in low:
        return False, L("密码错误或缺少密码", "Wrong or missing password"), None
    if "unexpected end of archive" in low or "missing volume" in low or "can not open the file as archive" in low:
        return False, L("分卷不完整或文件损坏", "Volumes missing or archive damaged"), None
    return False, (tail.strip().splitlines() or [f"exit {code}"])[-1][:300], None
