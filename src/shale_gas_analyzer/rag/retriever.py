"""Runtime retrieval from the local Chroma RAG store."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any

from dotenv import load_dotenv

from shale_gas_analyzer.rag import paths
from shale_gas_analyzer.rag.embeddings import embed_texts

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


COLLECTION_NAME = "shale_gas_engineering_knowledge"
MISSING_INDEX_MESSAGE = (
    "未检测到本地 RAG 知识库，请先运行：\n"
    "python -m shale_gas_analyzer.rag.build_index --mode update"
)

BILINGUAL_TERMS = {
    "井底积液": ["liquid loading", "gas well deliquification", "water loading", "gas well", "liquid"],
    "积液": ["liquid loading", "deliquification", "water loading", "liquid"],
    "携液": ["liquid loading", "critical liquid carrying", "critical flow", "gas well deliquification"],
    "泡沫排水": ["foam", "foaming agent", "foam deliquification", "gas well deliquification"],
    "泡排": ["foam", "foaming agent", "foam deliquification"],
    "柱塞": ["plunger lift", "plunger"],
    "间歇": ["intermittent production", "shut-in", "cyclic production"],
    "产量递减": ["production decline", "decline curve analysis", "decline curve", "Arps", "DCA"],
    "递减": ["decline", "decline curve analysis", "Arps"],
    "产量预测": ["production forecasting", "production prediction", "forecasting"],
    "预测": ["forecasting", "prediction", "production forecasting"],
    "页岩气": ["shale gas", "unconventional gas"],
    "气水比": ["gas water ratio", "water gas ratio", "water production"],
    "产水": ["water production", "produced water"],
    "日产气": ["gas production", "daily gas production"],
    "油压": ["tubing pressure", "wellhead pressure", "pressure"],
    "套压": ["casing pressure", "pressure"],
    "裂缝": ["fracture", "hydraulic fracturing", "fracture conductivity"],
    "能量衰竭": ["reservoir depletion", "pressure depletion", "depletion"],
    "机器学习": ["machine learning", "data-driven", "random forest", "XGBoost", "LSTM"],
}


class RagRetrievalError(RuntimeError):
    """Raised for user-visible retrieval failures."""


def rag_enabled() -> bool:
    return os.getenv("RAG_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"}


def _load_collection() -> Any:
    store_dir = paths.vector_store_dir()
    chunk_file = paths.chunks_jsonl_path()
    if (
        not store_dir.exists()
        or not any(store_dir.iterdir())
        or not paths.manifest_path().exists()
        or not chunk_file.exists()
        or chunk_file.stat().st_size == 0
    ):
        raise RagRetrievalError(MISSING_INDEX_MESSAGE)
    try:
        import chromadb
    except ImportError as exc:
        raise RagRetrievalError("缺少依赖 chromadb，请先安装 requirements.txt 中的依赖。") from exc
    try:
        client = chromadb.PersistentClient(path=str(store_dir))
        return client.get_collection(COLLECTION_NAME)
    except Exception as exc:
        raise RagRetrievalError(f"{MISSING_INDEX_MESSAGE}\nChroma 加载错误：{exc}") from exc


def retrieve_knowledge(query: str, top_k: int | None = None) -> list[dict[str, Any]]:
    load_dotenv()
    if not rag_enabled():
        raise RagRetrievalError("RAG 未启用。")
    query = (query or "").strip()
    if not query:
        raise RagRetrievalError("检索 query 不能为空。")

    top_k = top_k or int(os.getenv("RAG_TOP_K", "5"))
    min_pdf_results = min(max(int(os.getenv("RAG_MIN_PDF_RESULTS", "0")), 0), top_k)
    candidate_multiplier = max(int(os.getenv("RAG_CANDIDATE_MULTIPLIER", "6")), 1)
    candidate_count = max(top_k, top_k * candidate_multiplier)

    try:
        collection = _load_collection()
        query_embedding = embed_texts([query])[0]
        results = collection.query(query_embeddings=[query_embedding], n_results=candidate_count)
    except Exception as exc:
        return _keyword_fallback(query, top_k, min_pdf_results, reason=str(exc))

    documents = (results.get("documents") or [[]])[0]
    metadatas = (results.get("metadatas") or [[]])[0]
    distances = (results.get("distances") or [[]])[0]
    ids = (results.get("ids") or [[]])[0]

    candidates: list[dict[str, Any]] = []
    for index, document in enumerate(documents):
        distance = float(distances[index]) if index < len(distances) else 0.0
        metadata = dict(metadatas[index] or {}) if index < len(metadatas) else {}
        if index < len(ids):
            metadata.setdefault("chunk_id", ids[index])
        candidates.append(
            {
                "text": document,
                "score": 1.0 / (1.0 + max(distance, 0.0)),
                "metadata": metadata,
            }
        )
    return _balance_pdf_results(candidates, top_k=top_k, min_pdf_results=min_pdf_results)


def _keyword_fallback(query: str, top_k: int, min_pdf_results: int, reason: str) -> list[dict[str, Any]]:
    chunks = _load_chunks_jsonl()
    if not chunks:
        raise RagRetrievalError(f"Chroma 查询失败且 chunks.jsonl 不可用：{reason}")

    terms = _query_terms(query)
    candidates: list[dict[str, Any]] = []
    for chunk in chunks:
        text = str(chunk.get("text", ""))
        source_type = str(chunk.get("source_type", ""))
        haystack = f"{chunk.get('source_file', '')} {text}".lower()
        score = _keyword_score(haystack, terms)
        if score <= 0:
            continue
        if source_type == "pdf":
            score *= 1.08
        metadata = {
            "doc_id": chunk.get("doc_id", ""),
            "source_file": chunk.get("source_file", "未知来源"),
            "source_type": source_type,
            "page_start": chunk.get("page_start", 0),
            "page_end": chunk.get("page_end", 0),
            "chunk_id": chunk.get("chunk_id", ""),
            "retrieval_backend": "keyword_fallback",
            "fallback_reason": reason[:240],
        }
        candidates.append({"text": text, "score": score, "metadata": metadata})

    candidates.sort(key=lambda item: item["score"], reverse=True)
    if not candidates:
        candidates = _low_confidence_pdf_candidates(chunks, top_k, reason)
    return _balance_pdf_results(candidates, top_k=top_k, min_pdf_results=min_pdf_results)


def _load_chunks_jsonl() -> list[dict[str, Any]]:
    chunk_path = paths.chunks_jsonl_path()
    if not chunk_path.exists():
        return []
    chunks: list[dict[str, Any]] = []
    for line in chunk_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            chunks.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return chunks


def _query_terms(query: str) -> list[str]:
    lowered = query.lower()
    terms: list[str] = []

    for term in re.findall(r"[a-z0-9][a-z0-9_\-]{2,}", lowered):
        _append_term(terms, term)
    for term in re.findall(r"[\u4e00-\u9fff]{2,}", lowered):
        _append_term(terms, term)

    for chinese, english_terms in BILINGUAL_TERMS.items():
        if chinese in query:
            for english in english_terms:
                for part in english.lower().split():
                    _append_term(terms, part)
                _append_term(terms, english.lower())

    _append_term(terms, "shale")
    _append_term(terms, "gas")
    _append_term(terms, "production")
    return terms or [lowered.strip()]


def _append_term(terms: list[str], term: str) -> None:
    clean = term.strip().lower()
    if clean and clean not in terms:
        terms.append(clean)


def _keyword_score(text: str, terms: list[str]) -> float:
    score = 0.0
    for term in terms:
        if not term:
            continue
        count = text.count(term)
        if count:
            weight = 1.6 if " " in term else 1.0
            score += weight * min(count, 6) / max(len(terms), 1)
    return score


def _low_confidence_pdf_candidates(chunks: list[dict[str, Any]], top_k: int, reason: str) -> list[dict[str, Any]]:
    pdf_chunks = [chunk for chunk in chunks if chunk.get("source_type") == "pdf"]
    return [
        {
            "text": str(chunk.get("text", "")),
            "score": 0.01,
            "metadata": {
                "doc_id": chunk.get("doc_id", ""),
                "source_file": chunk.get("source_file", "未知来源"),
                "source_type": chunk.get("source_type", ""),
                "page_start": chunk.get("page_start", 0),
                "page_end": chunk.get("page_end", 0),
                "chunk_id": chunk.get("chunk_id", ""),
                "retrieval_backend": "keyword_fallback_low_confidence",
                "fallback_reason": reason[:240],
            },
        }
        for chunk in pdf_chunks[: max(top_k * 2, top_k)]
    ]


def _balance_pdf_results(candidates: list[dict[str, Any]], top_k: int, min_pdf_results: int) -> list[dict[str, Any]]:
    """Return top results while optionally keeping paper PDF evidence visible."""
    selected = candidates[:top_k]
    if min_pdf_results <= 0:
        return selected

    selected_ids = {item.get("metadata", {}).get("chunk_id") for item in selected}
    selected_pdf_count = sum(1 for item in selected if item.get("metadata", {}).get("source_type") == "pdf")
    needed = min_pdf_results - selected_pdf_count
    if needed <= 0:
        return selected

    pdf_candidates = [
        item
        for item in candidates[top_k:]
        if item.get("metadata", {}).get("source_type") == "pdf"
        and item.get("metadata", {}).get("chunk_id") not in selected_ids
    ]
    if not pdf_candidates:
        return selected

    replacements = pdf_candidates[:needed]
    keep_count = max(top_k - len(replacements), 0)
    return selected[:keep_count] + replacements


def _format_cli_result(query: str, results: list[dict[str, Any]]) -> str:
    lines = [
        "RAG 检索状态：已启用",
        f"检索 query：{query}",
        f"返回结果数量：{len(results)}",
    ]
    if not results:
        lines.append("未检索到相关知识。")
        return "\n".join(lines)
    for index, result in enumerate(results, start=1):
        metadata = result["metadata"]
        lines.extend(
            [
                "",
                f"结果 {index}，score={result['score']:.4f}",
                f"来源：{metadata.get('source_file', '未知来源')}",
                f"页码：{metadata.get('page_start', 0)}-{metadata.get('page_end', 0)}",
                f"检索后端：{metadata.get('retrieval_backend', 'chroma')}",
                result["text"],
            ]
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Query the local shale gas RAG knowledge base.")
    parser.add_argument("query", nargs="?", default="", help="检索问题")
    parser.add_argument("--top-k", type=int, default=None, help="返回结果数量")
    args = parser.parse_args()

    try:
        results = retrieve_knowledge(args.query, args.top_k)
        print(_format_cli_result(args.query, results))
    except RagRetrievalError as exc:
        print(f"RAG 检索状态：{'已启用' if rag_enabled() else '未启用'}")
        print(f"检索 query：{args.query}")
        print("返回结果数量：0")
        print(exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
