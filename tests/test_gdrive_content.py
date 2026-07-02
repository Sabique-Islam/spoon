from app.connectors.gdrive_content import extract_text


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
