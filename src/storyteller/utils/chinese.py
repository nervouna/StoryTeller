"""Chinese text utilities for web novel formatting."""
from __future__ import annotations

import re

_CJK_RE = re.compile(r"[一-鿿]")
_WHITESPACE_RE = re.compile(r"\s+")


def count_chinese_chars(text: str) -> int:
    """Count CJK characters (excluding punctuation)."""
    return len(_CJK_RE.findall(text))


def split_chapter(text: str, target_chars: int = 2500) -> list[str]:
    """Split a chapter into parts at paragraph boundaries.

    Tries to keep each part close to target_chars.
    """
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return [text]

    parts: list[str] = []
    current: list[str] = []
    current_len = 0

    for para in paragraphs:
        para_len = count_chinese_chars(para)
        if current_len + para_len > target_chars * 1.2 and current:
            parts.append("\n\n".join(current))
            current = [para]
            current_len = para_len
        else:
            current.append(para)
            current_len += para_len

    if current:
        parts.append("\n\n".join(current))
    return parts


def merge_short_sections(text: str, min_chars: int = 1500) -> list[str]:
    """Merge short sections to meet minimum length."""
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return [text]

    parts: list[str] = []
    current: list[str] = []
    current_len = 0

    for para in paragraphs:
        para_len = count_chinese_chars(para)
        current.append(para)
        current_len += para_len
        if current_len >= min_chars:
            parts.append("\n\n".join(current))
            current = []
            current_len = 0

    if current:
        if parts:
            # Merge remainder into last part
            parts[-1] += "\n\n" + "\n\n".join(current)
        else:
            parts.append("\n\n".join(current))
    return parts
