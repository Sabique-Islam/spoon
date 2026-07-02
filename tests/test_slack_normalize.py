from app.connectors.slack import (
    channel_to_document,
    emoji_to_document,
    file_to_document,
    message_to_text,
    team_to_document,
    user_to_document,
    usergroup_to_document,
)


def test_message_to_text():
    users = {"U123": "alice"}
    message = {"user": "U123", "ts": "1609459200.000000", "text": "Hello team"}
    text = message_to_text(message, users)
    assert "alice" in text
    assert "Hello team" in text


def test_message_to_text_with_reactions():
    users = {"U123": "alice"}
    message = {
        "user": "U123",
        "ts": "1609459200.000000",
        "text": "Nice",
        "reactions": [{"name": "thumbsup", "count": 2}],
    }
    text = message_to_text(message, users)
    assert ":thumbsup:" in text


def test_team_to_document():
    team = {"id": "T1", "name": "Acme", "domain": "acme", "email_domain": "acme.com"}
    doc = team_to_document(team)
    assert doc is not None
    assert doc.id == "slack-team-T1"
    assert "Acme" in doc.content
    assert doc.url == "https://acme.slack.com"


def test_user_to_document():
    member = {
        "id": "U123",
        "name": "alice",
        "profile": {
            "display_name": "alice",
            "real_name": "Alice Smith",
            "title": "Engineer",
            "email": "alice@acme.com",
        },
        "tz_label": "Pacific",
    }
    doc = user_to_document(member)
    assert doc is not None
    assert doc.id == "slack-user-U123"
    assert "Engineer" in doc.content
    assert "alice@acme.com" in doc.content


def test_usergroup_to_document():
    group = {
        "id": "S1",
        "handle": "eng",
        "name": "Engineering",
        "description": "Eng team",
        "user_count": 2,
    }
    doc = usergroup_to_document(group, ["alice", "bob"], "acme")
    assert doc is not None
    assert "@eng" in doc.title
    assert "alice, bob" in doc.content


def test_file_to_document():
    file_obj = {
        "id": "F1",
        "name": "notes.txt",
        "title": "Meeting notes",
        "mimetype": "text/plain",
        "user": "U123",
        "created": 1609459200,
        "permalink": "https://acme.slack.com/files/F1",
        "initial_comment": "From standup",
    }
    doc = file_to_document(file_obj, {"U123": "alice"})
    assert doc is not None
    assert doc.id == "slack-file-F1"
    assert "Meeting notes" in doc.content
    assert "From standup" in doc.content


def test_emoji_to_document():
    doc = emoji_to_document({"party_parrot": "https://emoji/parrot.gif"}, "acme")
    assert doc is not None
    assert doc.id == "slack-emoji"
    assert ":party_parrot:" in doc.content


def test_channel_to_document():
    channel = {
        "id": "C123",
        "name": "general",
        "is_private": False,
        "topic": {"value": "Announcements"},
        "purpose": {"value": "Company-wide updates"},
    }
    messages = [
        {"user": "U123", "ts": "1609459200.000000", "text": "First message"},
        {"user": "U456", "ts": "1609459300.000000", "text": "Second message"},
    ]
    users = {"U123": "alice", "U456": "bob"}

    doc = channel_to_document(
        channel,
        messages,
        users,
        "acme",
        pins=[{"type": "message", "message": messages[0]}],
        bookmarks=[{"title": "Wiki", "link": "https://wiki.acme.com", "emoji": ":book:"}],
        members=["alice", "bob"],
    )
    assert doc is not None
    assert doc.id == "slack-channel-C123"
    assert doc.source == "slack"
    assert doc.title == "#general"
    assert "Announcements" in doc.content
    assert "First message" in doc.content
    assert "Pinned message" in doc.content
    assert "Wiki" in doc.content
    assert "alice, bob" in doc.content
    assert "acme.slack.com/archives/C123" in doc.url


def test_channel_to_document_thread_reply():
    channel = {"id": "C123", "name": "general"}
    messages = [
        {"user": "U123", "ts": "1", "text": "parent"},
        {"text": "  ↳ [bob] (2021-01-01 00:00:00): reply", "subtype": "thread_reply"},
    ]
    doc = channel_to_document(channel, messages, {"U123": "alice"}, "acme")
    assert doc is not None
    assert "parent" in doc.content
    assert "reply" in doc.content


def test_channel_to_document_empty():
    channel = {"id": "C999", "name": "empty"}
    assert channel_to_document(channel, [], {}, None) is None
