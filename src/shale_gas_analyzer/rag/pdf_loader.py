"""PDF text extraction for local RAG indexing."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def load_pdf_pages(pdf_path: str | Path) -> tuple[list[dict[str, Any]], str | None]:
    """Extract text page by page from a text-based PDF.

    Returns (pages, error). Corrupt or unreadable PDFs are reported through the
    error string so the indexing flow can continue with other documents.
    """
    path = Path(pdf_path)
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return [], "缺少依赖 pymupdf，请先安装 requirements.txt 中的依赖。"

    try:
        document = fitz.open(path)
    except Exception as exc:
        return [], f"PDF 无法读取：{path.name}；错误：{exc}"

    pages: list[dict[str, Any]] = []
    try:
        for index, page in enumerate(document, start=1):
            try:
                text = page.get_text("text") or ""
            except Exception as exc:
                return [], f"PDF 第 {index} 页提取失败：{path.name}；错误：{exc}"
            pages.append(
                {
                    "source_file": path.name,
                    "source_path": str(path),
                    "page": index,
                    "text": text,
                }
            )
    finally:
        document.close()

    return pages, None


def load_pdfs(pdf_dir: str | Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Load all PDFs under a directory and collect non-fatal errors."""
    pages: list[dict[str, Any]] = []
    errors: list[str] = []
    for pdf_path in sorted(Path(pdf_dir).glob("*.pdf")):
        loaded, error = load_pdf_pages(pdf_path)
        if error:
            errors.append(error)
            continue
        pages.extend(loaded)
    return pages, errors
