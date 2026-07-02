from app.connectors.notion import (
    block_to_text,
    blocks_to_plain_text,
    extract_title,
    page_to_document,
)


def test_extract_title_from_page():
    page = {
        "id": "abc-123",
        "properties": {
            "Name": {
                "type": "title",
                "title": [{"plain_text": "My Page"}],
            }
        },
    }
    assert extract_title(page) == "My Page"


def test_extract_title_untitled():
    assert extract_title({"properties": {}}) == "Untitled"


def test_block_to_text_paragraph():
    block = {
        "type": "paragraph",
        "paragraph": {"rich_text": [{"plain_text": "Hello world"}]},
    }
    assert block_to_text(block) == "Hello world"


def test_block_to_text_heading():
    block = {
        "type": "heading_1",
        "heading_1": {"rich_text": [{"plain_text": "Title"}]},
    }
    assert block_to_text(block) == "Title"


def test_blocks_to_plain_text_nested():
    blocks = [
        {
            "type": "paragraph",
            "paragraph": {"rich_text": [{"plain_text": "Line 1"}]},
        },
        {
            "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": [{"plain_text": "Item"}]},
            "children": [
                {
                    "type": "paragraph",
                    "paragraph": {"rich_text": [{"plain_text": "Nested"}]},
                }
            ],
        },
    ]
    text = blocks_to_plain_text(blocks)
    assert "Line 1" in text
    assert "Item" in text
    assert "Nested" in text


def test_page_to_document():
    page = {
        "id": "abc-def-123",
        "object": "page",
        "last_edited_time": "2024-01-01T00:00:00.000Z",
        "created_time": "2023-01-01T00:00:00.000Z",
        "properties": {
            "title": {
                "type": "title",
                "title": [{"plain_text": "Test Page"}],
            }
        },
    }
    doc = page_to_document(page, "Page content here")
    assert doc.id == "notion-abc-def-123"
    assert doc.source == "notion"
    assert doc.title == "Test Page"
    assert doc.content == "Page content here"
    assert doc.url == "https://www.notion.so/abcdef123"
    assert doc.metadata["page_id"] == "abc-def-123"
