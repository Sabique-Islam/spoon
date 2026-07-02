import base64

from app.connectors.gmail import _extract_body, _html_to_text, message_to_document


def test_extract_body_plain():
    payload = {
        "mimeType": "text/plain",
        "body": {"data": base64.urlsafe_b64encode(b"Hello inbox").decode()},
    }
    plain, html = _extract_body(payload)
    assert plain == "Hello inbox"
    assert html == ""


def test_extract_body_multipart():
    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {
                "mimeType": "text/plain",
                "body": {"data": base64.urlsafe_b64encode(b"Plain body").decode()},
            },
            {
                "mimeType": "text/html",
                "body": {
                    "data": base64.urlsafe_b64encode(
                        b"<p>HTML <strong>body</strong></p>"
                    ).decode()
                },
            },
        ],
    }
    plain, html = _extract_body(payload)
    assert plain == "Plain body"
    assert "HTML" in html


def test_html_to_text():
    assert _html_to_text("<p>Hello <b>world</b></p>") == "Hello world"


def test_message_to_document():
    message = {
        "id": "msg-1",
        "threadId": "thread-1",
        "snippet": "Preview",
        "labelIds": ["INBOX"],
        "payload": {
            "headers": [
                {"name": "Subject", "value": "Weekly update"},
                {"name": "From", "value": "alice@acme.com"},
                {"name": "To", "value": "team@acme.com"},
                {"name": "Date", "value": "Mon, 1 Jan 2024 00:00:00 +0000"},
            ],
            "mimeType": "text/plain",
            "body": {
                "data": base64.urlsafe_b64encode(b"Status is green.").decode()
            },
        },
    }

    doc = message_to_document(message)
    assert doc is not None
    assert doc.id == "gmail-msg-1"
    assert doc.source == "gmail"
    assert doc.title == "Weekly update"
    assert "alice@acme.com" in doc.content
    assert "Status is green." in doc.content
    assert "mail.google.com" in doc.url


def test_message_to_document_empty_body():
    message = {
        "id": "msg-2",
        "payload": {
            "headers": [{"name": "Subject", "value": "Empty"}],
            "mimeType": "text/plain",
            "body": {},
        },
    }
    assert message_to_document(message) is None
