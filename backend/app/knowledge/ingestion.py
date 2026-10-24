"""Document parsing and chunking.

Formats: PDF (pypdf), plain text, Markdown (treated as text; structure-aware
splitting can come later without interface changes).
"""

from __future__ import annotations

import io
from dataclasses import dataclass

SUPPORTED_MIME = {
    "application/pdf": "pdf",
    "text/plain": "text",
    "text/markdown": "text",
    "text/x-markdown": "text",
}
SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md", ".markdown"}

CHUNK_SIZE_CHARS = 1200
CHUNK_OVERLAP_CHARS = 180
MAX_TEXT_CHARS = 2_000_000  # hard stop against pathological documents


@dataclass(frozen=True)
class ParsedDocument:
    text: str
    mime_type: str


def detect_kind(filename: str, mime_type: str) -> str | None:
    """Normalize to 'pdf' | 'text' | None (unsupported)."""
    kind = SUPPORTED_MIME.get((mime_type or "").split(";")[0].strip().lower())
    if kind:
        return kind
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in {".pdf"}:
        return "pdf"
    if ext in {".txt", ".md", ".markdown"}:
        return "text"
    return None


def parse_document(data: bytes, filename: str, mime_type: str) -> ParsedDocument:
    kind = detect_kind(filename, mime_type)
    if kind is None:
        raise ValueError(f"Unsupported document type: {filename!r} ({mime_type or 'unknown'})")
    if len(data) > 50 * 1024 * 1024:
        raise ValueError("Document exceeds the 50 MB limit")

    if kind == "pdf":
        from pypdf import PdfReader

        try:
            reader = PdfReader(io.BytesIO(data))
            pages = [page.extract_text() or "" for page in reader.pages]
            text = "\n\n".join(pages)
        except Exception as exc:  # corrupted/encrypted PDFs raise many shapes
            raise ValueError(f"Could not parse PDF: {exc}") from exc
        return ParsedDocument(text=text[:MAX_TEXT_CHARS], mime_type="application/pdf")

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("latin-1", errors="replace")
    return ParsedDocument(text=text[:MAX_TEXT_CHARS], mime_type="text/plain")


def chunk_text(text: str, size: int = CHUNK_SIZE_CHARS, overlap: int = CHUNK_OVERLAP_CHARS) -> list[str]:
    """Paragraph-aware sliding-window chunking.

    Prefers splitting on blank lines, then sentences, so chunks stay readable
    and citable. Empty/whitespace chunks are dropped.
    """
    text = text.strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            # try to break at a paragraph or sentence boundary inside the tail
            window = text[start:end]
            for sep in ("\n\n", ". ", "\n", " "):
                cut = window.rfind(sep)
                if cut > size // 2:
                    end = start + cut + len(sep)
                    break
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks
