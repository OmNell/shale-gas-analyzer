"""Conservative text cleanup for PDF and Markdown knowledge documents."""

from __future__ import annotations

import re


_PAGE_NUMBER_RE = re.compile(r"^\s*(?:第\s*)?\d{1,5}\s*(?:页|/\s*\d{1,5})?\s*$")


def clean_text(text: str) -> str:
    """Clean obvious extraction noise without rewriting technical content."""
    if not text:
        return ""

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"[ \t\f\v]+", " ", normalized)
    raw_lines = [line.strip() for line in normalized.split("\n")]

    lines: list[str] = []
    for line in raw_lines:
        if not line:
            lines.append("")
            continue
        if _PAGE_NUMBER_RE.match(line):
            continue
        if len(line) <= 1 and not re.search(r"[A-Za-z0-9\u4e00-\u9fff]", line):
            continue
        lines.append(line)

    merged: list[str] = []
    for line in lines:
        if not line:
            if merged and merged[-1]:
                merged.append("")
            continue
        if merged and merged[-1] and _should_merge(merged[-1], line):
            merged[-1] = f"{merged[-1]}{line}"
        else:
            merged.append(line)

    cleaned = "\n".join(merged)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _should_merge(previous: str, current: str) -> bool:
    if previous.endswith((".", "。", "；", ";", ":", "：", "!", "！", "?", "？", ")", "）")):
        return False
    if current.startswith(("#", "-", "*", "1.", "2.", "3.", "4.", "5.")):
        return False
    if len(previous) < 18:
        return False
    return True
