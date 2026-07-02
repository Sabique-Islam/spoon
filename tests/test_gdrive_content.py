import io
import zipfile

import pytest

from app.connectors.gdrive_content import _is_suspicious_zip, extract_text


def test_extract_text_plain():
    assert extract_text("notes.txt", "text/plain", b"Hello Drive") == "Hello Drive"


def test_extract_text_json():
    assert extract_text("data.json", "application/json", b'{"key": "value"}') == '{"key": "value"}'


def test_extract_text_html():
    text = extract_text(
        "page.html",
        "text/html",
        b"<html><body><p>Hello</p><p>World</p></body></html>",
    )
    assert "Hello" in text
    assert "World" in text


def test_extract_text_pdf():
    try:
        from pypdf import PdfWriter
    except ImportError:
        return

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = __import__("io").BytesIO()
    writer.write(buffer)
    # Blank PDF has no text; ensure handler runs without error.
    assert extract_text("blank.pdf", "application/pdf", buffer.getvalue()) in (None, "")


def _make_zip(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_is_suspicious_zip_flags_high_compression_ratio():
    # 10MB of a single repeated byte compresses to almost nothing —
    # a classic zip-bomb shape (huge decompressed / compressed ratio).
    bomb = _make_zip({"a.xml": b"0" * 10_000_000})
    assert _is_suspicious_zip(bomb) is True


def test_is_suspicious_zip_allows_normal_archive():
    normal = _make_zip({"document.xml": b"<root>hello world</root>"})
    assert _is_suspicious_zip(normal) is False


def test_is_suspicious_zip_ignores_non_zip_data():
    assert _is_suspicious_zip(b"not a zip file at all") is False


def test_extract_docx_skips_suspicious_archive(monkeypatch):
    from app.connectors import gdrive_content

    monkeypatch.setattr(gdrive_content, "_is_suspicious_zip", lambda data: True)
    assert gdrive_content._extract_docx(b"irrelevant") is None


def test_extract_pdf_skips_huge_page_count(monkeypatch):
    try:
        import pypdf
    except ImportError:
        pytest.skip("pypdf not installed")

    from app.connectors.gdrive_content import _MAX_PDF_PAGES, _extract_pdf

    class _FakePage:
        def extract_text(self):
            return "page"

    class _FakeReader:
        pages = [_FakePage()] * (_MAX_PDF_PAGES + 1)

    monkeypatch.setattr(pypdf, "PdfReader", lambda _data: _FakeReader())
    assert _extract_pdf(b"%PDF-1.4") is None
