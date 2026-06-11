"""Manifest management for local RAG indexing."""

from __future__ import annotations

import json
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from shale_gas_analyzer.rag import paths


def file_sha256(file_path: str | Path) -> str:
    digest = sha256()
    with Path(file_path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_manifest() -> dict[str, Any]:
    manifest_file = paths.manifest_path()
    if not manifest_file.exists():
        return {"documents": {}}
    try:
        return json.loads(manifest_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"documents": {}}


def save_manifest(manifest: dict[str, Any]) -> None:
    paths.processed_dir().mkdir(parents=True, exist_ok=True)
    paths.manifest_path().write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def manifest_key(file_path: str | Path) -> str:
    return Path(file_path).resolve().relative_to(paths.project_root()).as_posix()


def discover_source_files() -> list[Path]:
    pdfs = sorted(paths.raw_pdfs_dir().glob("*.pdf"))
    markdown = sorted(list(paths.manual_notes_dir().glob("*.md")) + list(paths.manual_notes_dir().glob("*.markdown")))
    return pdfs + markdown


def source_type_for(file_path: str | Path) -> str:
    suffix = Path(file_path).suffix.lower()
    if suffix == ".pdf":
        return "pdf"
    if suffix in {".md", ".markdown"}:
        return "markdown"
    raise ValueError(f"不支持的知识文件类型：{file_path}")


def needs_processing(
    manifest: dict[str, Any],
    file_path: str | Path,
    file_hash: str,
    chunk_size: int,
    chunk_overlap: int,
    embedding_model: str,
) -> bool:
    record = manifest.get("documents", {}).get(manifest_key(file_path))
    if not record:
        return True
    return any(
        [
            record.get("file_hash") != file_hash,
            record.get("chunk_size") != chunk_size,
            record.get("chunk_overlap") != chunk_overlap,
            record.get("embedding_model") != embedding_model,
        ]
    )


def removed_document_records(manifest: dict[str, Any], current_files: list[Path]) -> list[dict[str, Any]]:
    current_keys = {manifest_key(path) for path in current_files}
    documents = manifest.get("documents", {})
    return [record | {"manifest_key": key} for key, record in documents.items() if key not in current_keys]


def update_document_record(
    manifest: dict[str, Any],
    file_path: str | Path,
    doc_id: str,
    file_hash: str,
    chunk_size: int,
    chunk_overlap: int,
    embedding_model: str,
    chunk_count: int,
) -> None:
    path = Path(file_path)
    manifest.setdefault("documents", {})[manifest_key(path)] = {
        "doc_id": doc_id,
        "source_file": path.name,
        "file_path": manifest_key(path),
        "file_hash": file_hash,
        "file_size": path.stat().st_size,
        "source_type": source_type_for(path),
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
        "embedding_model": embedding_model,
        "chunk_count": chunk_count,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def remove_document_record(manifest: dict[str, Any], key: str) -> None:
    manifest.setdefault("documents", {}).pop(key, None)
