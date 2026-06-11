"""Embedding API wrapper for local RAG indexing and retrieval."""

from __future__ import annotations

import os


class EmbeddingError(RuntimeError):
    """Raised when embedding configuration or API calls fail."""


def embedding_model() -> str:
    return os.getenv("RAG_EMBEDDING_MODEL", "text-embedding-3-small")


def embedding_config() -> tuple[str, str, str]:
    model = embedding_model()
    base_url = os.getenv("RAG_EMBEDDING_BASE_URL") or os.getenv("OPENAI_API_BASE") or ""
    api_key = os.getenv("RAG_EMBEDDING_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
    if not base_url:
        raise EmbeddingError("未配置 RAG_EMBEDDING_BASE_URL 或 OPENAI_API_BASE。")
    if not api_key:
        raise EmbeddingError("未配置 RAG_EMBEDDING_API_KEY 或 OPENAI_API_KEY。")
    return model, base_url, api_key


def embed_texts(texts: list[str], batch_size: int = 64) -> list[list[float]]:
    if not texts:
        return []
    try:
        from litellm import embedding
    except ImportError as exc:
        raise EmbeddingError("缺少依赖 litellm，请先安装 requirements.txt 中的依赖。") from exc

    model, base_url, api_key = embedding_config()
    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        try:
            response = embedding(model=model, input=batch, api_base=base_url, api_key=api_key)
        except Exception as exc:
            raise EmbeddingError(f"Embedding API 调用失败：{exc}") from exc
        data = response.get("data") if isinstance(response, dict) else getattr(response, "data", None)
        if not data:
            raise EmbeddingError("Embedding API 未返回向量数据。")
        for item in data:
            vector = item.get("embedding") if isinstance(item, dict) else getattr(item, "embedding", None)
            if vector is None:
                raise EmbeddingError("Embedding API 返回格式缺少 embedding 字段。")
            vectors.append(list(vector))
    return vectors
