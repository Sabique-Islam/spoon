from app.connectors.outlook import _html_to_text, message_to_document


def test_html_to_text():
    assert _html_to_text("<p>Hello <b>Outlook</b></p>") == "Hello Outlook"


def test_message_to_document():
    message = {
        "id": "msg-1",
        "subject": "Weekly update",
        "from": {"emailAddress": {"name": "Alice", "address": "alice@acme.com"}},
        "toRecipients": [
            {"emailAddress": {"name": "Bob", "address": "bob@acme.com"}}
        ],
        "ccRecipients": [],
        "receivedDateTime": "2024-01-01T00:00:00Z",
        "body": {"contentType": "text", "content": "Status is green."},
        "webLink": "https://outlook.office.com/mail/id/msg-1",
        "conversationId": "conv-1",
        "isDraft": False,
    }

    doc = message_to_document(message)
    assert doc is not None
    assert doc.id == "outlook-msg-1"
    assert doc.source == "outlook"
    assert doc.title == "Weekly update"
    assert "alice@acme.com" in doc.content
    assert "Status is green." in doc.content
    assert doc.url.startswith("https://outlook.office.com")


def test_message_to_document_html_body():
    message = {
        "id": "msg-2",
        "subject": "HTML mail",
        "from": {"emailAddress": {"address": "alice@acme.com"}},
        "toRecipients": [{"emailAddress": {"address": "bob@acme.com"}}],
        "body": {"contentType": "html", "content": "<p>HTML body</p>"},
        "isDraft": False,
    }
    doc = message_to_document(message)
    assert doc is not None
    assert "HTML body" in doc.content


def test_message_to_document_skips_draft():
    message = {
        "id": "msg-3",
        "subject": "Draft",
        "body": {"contentType": "text", "content": "draft"},
        "isDraft": True,
    }
    assert message_to_document(message) is None


def test_message_to_document_empty_body():
    message = {
        "id": "msg-4",
        "subject": "Empty",
        "body": {"contentType": "text", "content": "   "},
        "bodyPreview": "",
        "isDraft": False,
    }
    assert message_to_document(message) is None
