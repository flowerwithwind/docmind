"""文本处理工具：清洗、分句、分词、数值/日期归一化、token 估算。"""
from __future__ import annotations

import re
import unicodedata

_SPACE_RE = re.compile(r"\s+")
_NUM_CLEAN_RE = re.compile(r"[^\d.\-]")
_CN_NUM_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*([万亿])")
_DATE_CN_RE = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?")
_DATE_DASH_RE = re.compile(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})")


def clean_text(text: str) -> str:
    """压缩空白、统一标点宽度。"""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    return _SPACE_RE.sub(" ", text).strip()


def split_sentences(text: str, max_len: int = 120) -> list[str]:
    """按中文/英文句末标点切句，长句按逗号兜底。"""
    parts: list[str] = []
    buf = ""
    for ch in text:
        buf += ch
        if ch in "。！？!?；;\n":
            parts.append(buf.strip())
            buf = ""
    if buf.strip():
        parts.append(buf.strip())
    out: list[str] = []
    for p in parts:
        if len(p) <= max_len:
            out.append(p)
        else:
            seg = ""
            for ch in p:
                seg += ch
                if ch in "，,、：: " and len(seg) >= max_len * 0.6:
                    out.append(seg.strip())
                    seg = ""
            if seg.strip():
                out.append(seg.strip())
    return [p for p in out if p]


def tokenize(text: str) -> list[str]:
    """中文按 2-gram + 英文按词，返回小写 token 列表。"""
    tokens: list[str] = []
    for word in re.findall(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]+", text.lower()):
        if re.fullmatch(r"[\u4e00-\u9fff]+", word):
            if len(word) == 1:
                tokens.append(word)
            else:
                tokens.extend(word[i : i + 2] for i in range(len(word) - 1))
        else:
            tokens.append(word)
    return tokens


def token_estimate(text: str) -> int:
    """粗略估算 token 数（中英混合）。"""
    if not text:
        return 0
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    other = len(text) - cjk
    return max(1, int(cjk * 0.6 + other * 0.28))


def normalize_number(value: str) -> float | None:
    """把 '￥1,200,000.00' / '120万元' / '12.5%' 归一化为数字。"""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    neg = s.startswith("-")
    s = s.replace("（", "(").replace("）", ")")
    m = re.search(r"\(([\d.\-]+)\)", s)  # 会计负号 (120)
    if m:
        return -abs(float(m.group(1)))
    multiplier = 1.0
    m = _CN_NUM_RE.search(s)
    if m:
        s = m.group(1)
        multiplier = 100000000 if m.group(2) == "亿" else 10000
    s = _NUM_CLEAN_RE.sub("", s)
    if s in ("", "-", "."):
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    if neg:
        v = -abs(v)
    return v * multiplier


def normalize_date(value: str) -> str | None:
    """把 '2026年3月15日' / '2026-03-15' 归一化为 ISO 日期。"""
    if value is None:
        return None
    s = str(value).strip()
    m = _DATE_CN_RE.search(s) or _DATE_DASH_RE.search(s)
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if not (1 <= mo <= 12 and 1 <= d <= 31):
        return None
    return f"{y:04d}-{mo:02d}-{d:02d}"


def truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "…"


def first_line(text: str, limit: int = 30) -> str:
    line = (text or "").strip().splitlines()[0] if text.strip() else ""
    return truncate(line, limit)
