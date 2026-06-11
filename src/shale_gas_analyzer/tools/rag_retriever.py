"""CrewAI tool for retrieving local shale gas engineering knowledge."""

from __future__ import annotations

import os

try:
    from crewai.tools import tool
except ImportError:  # pragma: no cover - compatibility with some CrewAI releases
    from crewai_tools import tool

from shale_gas_analyzer.rag.retriever import RagRetrievalError, rag_enabled, retrieve_knowledge


@tool("retrieve_engineering_knowledge_tool")
def retrieve_engineering_knowledge_tool(query: str) -> str:
    """Retrieve local PDF/Markdown engineering knowledge for shale gas diagnosis."""
    if not rag_enabled():
        message = "RAG 未启用。"
        print(f"[RAG] {message}", flush=True)
        return message

    top_k = int(os.getenv("RAG_TOP_K", "5"))
    print(f"[RAG] query={query} top_k={top_k}", flush=True)
    try:
        results = retrieve_knowledge(query, top_k=top_k)
    except RagRetrievalError as exc:
        message = f"RAG 检索失败：{exc}"
        print(f"[RAG] {message}", flush=True)
        return message
    except Exception as exc:
        message = f"RAG 检索失败：{exc}"
        print(f"[RAG] {message}", flush=True)
        return message

    source_labels = [_source_label(result.get("metadata", {})) for result in results]
    print(f"[RAG] returned={len(results)} sources={'; '.join(source_labels) or 'none'}", flush=True)

    lines = [
        "[RAG检索结果]",
        "",
        "RAG 状态：已启用",
        f"检索问题：{query}",
        f"返回结果数量：{len(results)}",
        "来源列表：" + ("；".join(source_labels) if source_labels else "无"),
    ]
    if not results:
        lines.append("未检索到相关知识。")
        return "\n".join(lines)

    for index, result in enumerate(results, start=1):
        metadata = result.get("metadata", {})
        text = str(result.get("text", "")).strip()
        excerpt = text[:900] + ("..." if len(text) > 900 else "")
        lines.extend(
            [
                "",
                f"结果{index}：",
                f"来源：{_source_label(metadata)}",
                f"相关内容：{excerpt}",
                "启发：请结合生产数据指标判断该知识是否适用于当前井况，不得脱离数据直接套用。",
            ]
        )
    return "\n".join(lines)


def _source_label(metadata: dict) -> str:
    source_file = metadata.get("source_file", "未知来源")
    source_type = metadata.get("source_type", "")
    page_start = metadata.get("page_start", 0)
    page_end = metadata.get("page_end", 0)
    if source_type == "pdf" and page_start:
        return f"{source_file}，第 {page_start}-{page_end} 页"
    return str(source_file)
