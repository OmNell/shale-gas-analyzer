"""Centralized paths for the local RAG knowledge base."""

from __future__ import annotations

import os
from pathlib import Path


def project_root() -> Path:
    """Return the repository root path."""
    return Path(__file__).resolve().parents[3]


def _root_relative_env(name: str, default: str) -> Path:
    value = os.getenv(name, default)
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return project_root() / path


def knowledge_base_dir() -> Path:
    return _root_relative_env("RAG_KNOWLEDGE_DIR", "knowledge_base")


def raw_pdfs_dir() -> Path:
    return knowledge_base_dir() / "raw_pdfs"


def manual_notes_dir() -> Path:
    return knowledge_base_dir() / "manual_notes"


def processed_dir() -> Path:
    return knowledge_base_dir() / "processed"


def chunks_jsonl_path() -> Path:
    return processed_dir() / "chunks.jsonl"


def manifest_path() -> Path:
    return processed_dir() / "index_manifest.json"


def vector_store_dir() -> Path:
    return _root_relative_env("RAG_VECTOR_STORE_DIR", "vector_store/chroma")


def ensure_rag_dirs() -> None:
    """Create the local RAG directory skeleton if it is missing."""
    for path in (raw_pdfs_dir(), manual_notes_dir(), processed_dir(), vector_store_dir()):
        path.mkdir(parents=True, exist_ok=True)
