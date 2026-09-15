"""Unit tests: pdf_input block chunking, dispatch, errors, minimal PDF."""

import os
from pathlib import Path

import pytest

from gramophone_m1.pdf_input import read_blocks

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "fixtures" / "sample_chapter.md"


def _minimal_pdf(text: str) -> bytes:
    """Generate a tiny valid one-page PDF with correct xref offsets."""
    content = f"BT /F1 24 Tf 100 700 Td ({text}) Tj ET".encode("latin-1")
    bodies = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(bodies, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(bodies) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(bodies) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF\n"
    ).encode()
    return bytes(out)


def test_fixture_chunks_have_sequential_ids_and_page_zero():
    blocks = read_blocks(str(FIXTURE))
    assert len(blocks) >= 10
    assert [b["chunk_id"] for b in blocks] == [f"c{i:03d}" for i in range(1, len(blocks) + 1)]
    assert all(b["page"] == 0 for b in blocks)


def test_spans_round_trip_to_source_text():
    raw = FIXTURE.read_text(encoding="utf-8")
    for block in read_blocks(str(FIXTURE)):
        start, end = block["span"]
        assert raw[start:end] == block["text"]
        assert block["text"].strip()


def test_missing_file_raises_filenotfound():
    with pytest.raises(FileNotFoundError):
        read_blocks(str(ROOT / "fixtures" / "no_such_file.md"))


def test_unsupported_extension_raises_valueerror(tmp_path):
    bad = tmp_path / "x.foo"
    bad.write_text("hello", encoding="utf-8")
    with pytest.raises(ValueError):
        read_blocks(str(bad))


def test_txt_extension_reads_like_markdown(tmp_path):
    txt = tmp_path / "x.txt"
    txt.write_text("Para one.\n\nPara two.\n", encoding="utf-8")
    blocks = read_blocks(str(txt))
    assert [b["text"] for b in blocks] == ["Para one.", "Para two."]
    assert [b["chunk_id"] for b in blocks] == ["c001", "c002"]


def test_empty_markdown_yields_no_blocks(tmp_path):
    empty = tmp_path / "e.md"
    empty.write_text("\n\n   \n", encoding="utf-8")
    assert read_blocks(str(empty)) == []


def test_minimal_pdf_extracts_text_with_page_one(tmp_path):
    pdf = tmp_path / "mini.pdf"
    pdf.write_bytes(_minimal_pdf("Hypothesis Testing"))
    blocks = read_blocks(str(pdf))
    assert blocks
    assert all(b["page"] == 1 for b in blocks)
    assert "Hypothesis Testing" in "\n".join(b["text"] for b in blocks)
    assert [b["chunk_id"] for b in blocks] == [f"c{i:03d}" for i in range(1, len(blocks) + 1)]


def test_pdf_requires_pypdf(monkeypatch, tmp_path):
    import sys

    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    monkeypatch.setitem(sys.modules, "pypdf", None)
    with pytest.raises(RuntimeError, match="pypdf"):
        read_blocks(str(pdf))
