"""Document chunking for local RAG indexing."""

from __future__ import annotations

import os
from hashlib import sha256
from pathlib import Path
from typing import Any

from shale_gas_analyzer.rag.text_cleaner import clean_text


def chunk_config() -> tuple[int, int]:
    chunk_size = int(os.getenv("RAG_CHUNK_SIZE", "700"))
    chunk_overlap = int(os.getenv("RAG_CHUNK_OVERLAP", "100"))
    if chunk_size <= 0:
        raise ValueError("RAG_CHUNK_SIZE 必须大于 0")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("RAG_CHUNK_OVERLAP 必须大于等于 0 且小于 RAG_CHUNK_SIZE")
    return chunk_size, chunk_overlap


def stable_doc_id(file_path: str | Path, file_hash: str) -> str:
    seed = f"{Path(file_path).as_posix()}:{file_hash}".encode("utf-8")
    return f"doc_{sha256(seed).hexdigest()[:12]}"


def chunk_pdf_pages(
    pages: list[dict[str, Any]],
    doc_id: str,
    chunk_size: int,
    chunk_overlap: int,
) -> list[dict[str, Any]]:
    page_units = []
    for page in pages:
        text = clean_text(str(page.get("text", "")))
        if not text:
            continue
        page_units.append(
            {
                "text": text,
                "page_start": int(page["page"]),
                "page_end": int(page["page"]),
                "source_file": page["source_file"],
            }
        )
    return _chunk_units(page_units, doc_id, "pdf", chunk_size, chunk_overlap)


def chunk_markdown_file(
    md_path: str | Path,
    doc_id: str,
    chunk_size: int,
    chunk_overlap: int,
) -> list[dict[str, Any]]:
    path = Path(md_path)
    text = clean_text(path.read_text(encoding="utf-8"))
    units = [{"text": text, "page_start": 0, "page_end": 0, "source_file": path.name}] if text else []
    return _chunk_units(units, doc_id, "markdown", chunk_size, chunk_overlap)


def _chunk_units(
    units: list[dict[str, Any]],
    doc_id: str,
    source_type: str,
    chunk_size: int,
    chunk_overlap: int,
) -> list[dict[str, Any]]:
    if not units:
        return []

    source_file = str(units[0]["source_file"])
    chunks: list[dict[str, Any]] = []
    current_parts: list[str] = []
    current_len = 0
    page_start: int | None = None
    page_end: int | None = None

    for unit in units:
        paragraphs = _split_text(unit["text"], chunk_size)
        for paragraph in paragraphs:
            if current_parts and current_len + len(paragraph) + 1 > chunk_size:
                _append_chunk(chunks, doc_id, source_file, source_type, page_start, page_end, current_parts)
                current_parts = _overlap_parts(current_parts, chunk_overlap)
                current_len = sum(len(part) for part in current_parts)
                if not current_parts:
                    page_start = int(unit["page_start"])
                page_end = int(unit["page_end"])

            if not current_parts:
                page_start = int(unit["page_start"])
            current_parts.append(paragraph)
            current_len += len(paragraph) + 1
            page_end = int(unit["page_end"])

    if current_parts:
        _append_chunk(chunks, doc_id, source_file, source_type, page_start, page_end, current_parts)

    return chunks


def _split_text(text: str, chunk_size: int) -> list[str]:
    paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
    result: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph) <= chunk_size:
            result.append(paragraph)
            continue
        start = 0
        while start < len(paragraph):
            result.append(paragraph[start : start + chunk_size].strip())
            start += chunk_size
    return [part for part in result if part]


def _overlap_parts(parts: list[str], overlap: int) -> list[str]:
    if overlap <= 0:
        return []
    kept: list[str] = []
    total = 0
    for part in reversed(parts):
        if total >= overlap:
            break
        kept.insert(0, part)
        total += len(part)
    return kept


def _append_chunk(
    chunks: list[dict[str, Any]],
    doc_id: str,
    source_file: str,
    source_type: str,
    page_start: int | None,
    page_end: int | None,
    parts: list[str],
) -> None:
    text = "\n\n".join(part.strip() for part in parts if part.strip()).strip()
    if not text:
        return
    index = len(chunks) + 1
    chunks.append(
        {
            "chunk_id": f"{doc_id}_chunk_{index:04d}",
            "doc_id": doc_id,
            "source_file": source_file,
            "source_type": source_type,
            "page_start": page_start if source_type == "pdf" else 0,
            "page_end": page_end if source_type == "pdf" else 0,
            "text": text,
        }
    )
