"""Offline builder for the local RAG Chroma index."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from shale_gas_analyzer.rag import paths
from shale_gas_analyzer.rag.chunker import chunk_config, chunk_markdown_file, chunk_pdf_pages, stable_doc_id
from shale_gas_analyzer.rag.embeddings import EmbeddingError, embed_texts, embedding_model
from shale_gas_analyzer.rag.manifest import (
    discover_source_files,
    file_sha256,
    load_manifest,
    needs_processing,
    remove_document_record,
    removed_document_records,
    save_manifest,
    source_type_for,
    update_document_record,
)
from shale_gas_analyzer.rag.pdf_loader import load_pdf_pages
from shale_gas_analyzer.rag.retriever import COLLECTION_NAME


def load_chunks_jsonl() -> list[dict[str, Any]]:
    chunk_file = paths.chunks_jsonl_path()
    if not chunk_file.exists():
        return []
    chunks: list[dict[str, Any]] = []
    for line in chunk_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            chunks.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return chunks


def save_chunks_jsonl(chunks: list[dict[str, Any]]) -> None:
    paths.processed_dir().mkdir(parents=True, exist_ok=True)
    with paths.chunks_jsonl_path().open("w", encoding="utf-8") as handle:
        for chunk in chunks:
            handle.write(json.dumps(chunk, ensure_ascii=False) + "\n")


def get_collection() -> Any:
    try:
        import chromadb
    except ImportError as exc:
        raise RuntimeError("缺少依赖 chromadb，请先安装 requirements.txt 中的依赖。") from exc
    paths.vector_store_dir().mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(paths.vector_store_dir()))
    return client.get_or_create_collection(COLLECTION_NAME)


def delete_doc_chunks(collection: Any | None, doc_id: str) -> None:
    if collection is None:
        return
    try:
        collection.delete(where={"doc_id": doc_id})
    except Exception:
        # Chroma raises when no matching rows exist in some versions.
        return


def add_chunks_to_chroma(collection: Any, chunks: list[dict[str, Any]]) -> int:
    if not chunks:
        return 0
    embeddings = embed_texts([chunk["text"] for chunk in chunks])
    metadatas = [
        {
            "doc_id": chunk["doc_id"],
            "source_file": chunk["source_file"],
            "source_type": chunk["source_type"],
            "page_start": chunk.get("page_start", 0),
            "page_end": chunk.get("page_end", 0),
            "chunk_id": chunk["chunk_id"],
        }
        for chunk in chunks
    ]
    collection.add(
        ids=[chunk["chunk_id"] for chunk in chunks],
        documents=[chunk["text"] for chunk in chunks],
        metadatas=metadatas,
        embeddings=embeddings,
    )
    return len(chunks)


def process_file(file_path: Path, doc_id: str, chunk_size: int, chunk_overlap: int) -> tuple[list[dict[str, Any]], str | None]:
    source_type = source_type_for(file_path)
    if source_type == "pdf":
        pages, error = load_pdf_pages(file_path)
        if error:
            return [], error
        return chunk_pdf_pages(pages, doc_id, chunk_size, chunk_overlap), None
    return chunk_markdown_file(file_path, doc_id, chunk_size, chunk_overlap), None


def run_status() -> None:
    load_dotenv()
    paths.ensure_rag_dirs()
    manifest = load_manifest()
    source_files = discover_source_files()
    pdf_count = sum(1 for path in source_files if path.suffix.lower() == ".pdf")
    md_count = sum(1 for path in source_files if path.suffix.lower() in {".md", ".markdown"})
    chunks = load_chunks_jsonl()
    chunk_size, chunk_overlap = chunk_config()
    model = embedding_model()

    pending = []
    for file_path in source_files:
        file_hash = file_sha256(file_path)
        if needs_processing(manifest, file_path, file_hash, chunk_size, chunk_overlap, model):
            pending.append(file_path.name)
    removed = removed_document_records(manifest, source_files)

    print("本地 RAG 知识库状态")
    print(f"raw_pdfs PDF 数量：{pdf_count}")
    print(f"manual_notes Markdown 数量：{md_count}")
    print(f"manifest 已记录文档数：{len(manifest.get('documents', {}))}")
    print(f"chunk 总数：{len(chunks)}")
    print(f"向量库路径：{paths.vector_store_dir()}")
    print(f"当前 chunk_size：{chunk_size}")
    print(f"当前 chunk_overlap：{chunk_overlap}")
    print(f"当前 embedding_model：{model}")
    print(f"是否存在未处理文件：{'是' if pending or removed else '否'}")
    if pending:
        print("待处理文件：" + "，".join(pending))
    if removed:
        print("待清理已删除文件：" + "，".join(str(item.get("file_path", item.get("source_file"))) for item in removed))


def run_update() -> None:
    load_dotenv()
    paths.ensure_rag_dirs()
    manifest = load_manifest()
    source_files = discover_source_files()
    pdf_count = sum(1 for path in source_files if path.suffix.lower() == ".pdf")
    md_count = sum(1 for path in source_files if path.suffix.lower() in {".md", ".markdown"})
    chunk_size, chunk_overlap = chunk_config()
    model = embedding_model()

    print(f"发现 PDF 数量：{pdf_count}")
    print(f"发现 Markdown 数量：{md_count}")

    if not source_files and not manifest.get("documents"):
        print("当前知识库为空：未发现 PDF 或 Markdown 文件。")
        save_manifest(manifest)
        save_chunks_jsonl([])
        print("manifest 更新成功")
        print(f"向量库路径：{paths.vector_store_dir()}")
        return

    existing_chunks = load_chunks_jsonl()
    collection = None
    changed_files: list[Path] = []
    file_hashes: dict[Path, str] = {}

    for file_path in source_files:
        file_hash = file_sha256(file_path)
        file_hashes[file_path] = file_hash
        if needs_processing(manifest, file_path, file_hash, chunk_size, chunk_overlap, model):
            changed_files.append(file_path)
        else:
            print(f"跳过未变化文件：{file_path.name}")

    removed = removed_document_records(manifest, source_files)
    if changed_files or removed:
        collection = get_collection()

    for record in removed:
        doc_id = str(record.get("doc_id", ""))
        if doc_id:
            delete_doc_chunks(collection, doc_id)
            existing_chunks = [chunk for chunk in existing_chunks if chunk.get("doc_id") != doc_id]
            print(f"删除已不存在文件的旧 chunks：{record.get('file_path', record.get('source_file'))}，doc_id={doc_id}")
        remove_document_record(manifest, str(record["manifest_key"]))

    total_written = 0
    for file_path in changed_files:
        file_hash = file_hashes[file_path]
        doc_id = stable_doc_id(file_path, file_hash)
        print(f"处理新增或修改文件：{file_path.name}")
        chunks, error = process_file(file_path, doc_id, chunk_size, chunk_overlap)
        if error:
            print(error)
            continue
        old_record = manifest.get("documents", {}).get(
            file_path.resolve().relative_to(paths.project_root()).as_posix(),
            {},
        )
        old_doc_id = old_record.get("doc_id", doc_id)
        delete_doc_chunks(collection, old_doc_id)
        if old_doc_id != doc_id:
            delete_doc_chunks(collection, doc_id)
        existing_chunks = [chunk for chunk in existing_chunks if chunk.get("doc_id") not in {old_doc_id, doc_id}]
        written = add_chunks_to_chroma(collection, chunks)
        total_written += written
        existing_chunks.extend(chunks)
        update_document_record(manifest, file_path, doc_id, file_hash, chunk_size, chunk_overlap, model, len(chunks))
        print(f"{file_path.name} 生成 chunks：{len(chunks)}")
        print(f"向量库写入条数：{written}")

    save_chunks_jsonl(existing_chunks)
    save_manifest(manifest)
    print(f"本次向量库总写入条数：{total_written}")
    print("manifest 更新成功")
    print(f"向量库路径：{paths.vector_store_dir()}")


def run_rebuild() -> None:
    load_dotenv()
    if paths.vector_store_dir().exists():
        shutil.rmtree(paths.vector_store_dir())
    paths.vector_store_dir().mkdir(parents=True, exist_ok=True)
    (paths.vector_store_dir() / ".gitkeep").write_text("", encoding="utf-8")
    if paths.chunks_jsonl_path().exists():
        paths.chunks_jsonl_path().unlink()
    save_manifest({"documents": {}})
    print("已清理旧向量库、chunks.jsonl 和 manifest，开始全量重建。")
    run_update()


def main() -> None:
    parser = argparse.ArgumentParser(description="Build or inspect the local shale gas RAG index.")
    parser.add_argument("--mode", choices=["update", "rebuild", "status"], default="update")
    args = parser.parse_args()

    try:
        if args.mode == "status":
            run_status()
        elif args.mode == "rebuild":
            run_rebuild()
        else:
            run_update()
    except (EmbeddingError, RuntimeError, ValueError) as exc:
        print(f"RAG 构建失败：{exc}")
        raise SystemExit(1) from exc
        print(f"RAG 构建失败：{exc}")


if __name__ == "__main__":
    main()
