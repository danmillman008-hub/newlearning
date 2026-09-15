"""Input stage: PDF (pypdf) or Markdown/Text -> text blocks.

Every block carries provenance-ready coordinates::

    {"chunk_id": "c001", "page": 0, "span": [start, end], "text": "..."}

- Markdown/Text: one logical page (page=0); span = char offsets into the file.
- PDF: page = 1-based PDF page number; span = char offsets into that page's text.
"""

from __future__ import annotations

import os
import re

_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")


def _chunk_text(text: str, page: int, start_index: int = 0) -> list[dict]:
    """Split page text on blank lines, keeping exact char offsets."""
    text = text.rstrip("\n")  # drop EOF newlines only; interior offsets shift-free
    blocks: list[dict] = []
    pos = 0
    idx = start_index
    for para in _PARAGRAPH_SPLIT.split(text):
        if para.strip():
            start = text.index(para, pos)
            end = start + len(para)
            idx += 1
            blocks.append(
                {
                    "chunk_id": f"c{idx:03d}",
                    "page": page,
                    "span": [start, end],
                    "text": para,
                }
            )
            pos = end
        else:
            pos += len(para)
    return blocks


def read_markdown(path: str) -> list[dict]:
    """Read a Markdown/Text file into blocks (page=0, char-offset spans)."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    return _chunk_text(text, page=0)


def read_pdf(path: str) -> list[dict]:
    """Read a PDF file into blocks via pypdf (lazy import, 1-based pages)."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError(
            "pdf_input: reading PDFs requires the 'pypdf' package "
            "(pip install pypdf)"
        ) from exc
    reader = PdfReader(path)
    blocks: list[dict] = []
    for pageno, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        blocks.extend(_chunk_text(text, page=pageno, start_index=len(blocks)))
    return blocks


def read_blocks(path: str) -> list[dict]:
    """Read INPUT path (.md/.markdown/.txt/.pdf) into provenance blocks."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"pdf_input: input file not found: {path}")
    ext = os.path.splitext(path)[1].lower()
    if ext in (".md", ".markdown", ".txt"):
        return read_markdown(path)
    if ext == ".pdf":
        return read_pdf(path)
    raise ValueError(f"pdf_input: unsupported input extension {ext!r} for {path}")
