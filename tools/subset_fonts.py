"""Rebuild the console's bundled pixel fonts (dev tool).

The Chinese pixel font is large, so only the characters the console's static UI uses are kept.
Re-run this after changing UI strings:

    pip install fonttools brotli
    python tools/subset_fonts.py --pixel fusion-pixel-12px-proportional-zh_hans.ttf --vt323 VT323-Regular.ttf --caps Silkscreen-Regular.ttf

Sources (all SIL Open Font License 1.1):
  Fusion Pixel Font   https://github.com/TakWolf/fusion-pixel-font
  VT323               https://fonts.google.com/specimen/VT323
  Silkscreen          https://fonts.google.com/specimen/Silkscreen
"""
from __future__ import annotations

import argparse
import re
import string
from pathlib import Path

from fontTools import subset

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "tgagent" / "web"
OUT = WEB / "fonts"


def ui_characters() -> str:
    text = ""
    for f in list(WEB.glob("*.js")) + list(WEB.glob("*.html")) + [ROOT / "tgagent" / "tools.py"]:
        text += f.read_text("utf-8")
    cjk = set(re.findall(r"[　-〿㐀-鿿＀-￯·—…“”‘’]", text))
    return "".join(sorted(cjk)) + string.printable + "×▸→←↑↓⇄"


def build(src: str, dest: str, text: str | None = None, unicodes: str | None = None) -> None:
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.layout_features = ["*"]
    opts.name_IDs = ["*"]
    opts.notdef_outline = True
    font = subset.load_font(src, opts)
    sub = subset.Subsetter(opts)
    if text:
        sub.populate(text=text)
    else:
        sub.populate(unicodes=subset.parse_unicodes(unicodes))
    sub.subset(font)
    OUT.mkdir(parents=True, exist_ok=True)
    subset.save_font(font, str(OUT / dest), opts)
    print(f"{dest}: {(OUT / dest).stat().st_size // 1024} KB")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pixel", required=True, help="Fusion Pixel 12px proportional zh_hans TTF")
    ap.add_argument("--vt323", required=True)
    ap.add_argument("--caps", required=True, help="Silkscreen TTF")
    a = ap.parse_args()
    build(a.pixel, "pixel-zh.woff2", text=ui_characters())
    build(a.vt323, "vt323.woff2", unicodes="U+0020-007E,U+00B7,U+00D7,U+2026,U+2192,U+2190")
    build(a.caps, "silkscreen.woff2", unicodes="U+0020-007E,U+00D7")


if __name__ == "__main__":
    main()
