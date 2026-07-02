from app.connectors.gdrive import file_to_document


def test_file_to_document():
    file_meta = {
        "id": "file-abc",
        "name": "Notes.txt",
        "mimeType": "text/plain",
        "webViewLink": "https://drive.google.com/file/d/file-abc/view",
        "description": "Personal notes",
        "createdTime": "2024-01-01T00:00:00.000Z",
        "modifiedTime": "2024-01-02T00:00:00.000Z",
    }
    doc = file_to_document(file_meta, "Hello from Drive")
    assert doc.id == "gdrive-file-abc"
    assert doc.source == "gdrive"
    assert doc.title == "Notes.txt"
    assert "Hello from Drive" in doc.content
    assert "Personal notes" in doc.content
    assert doc.metadata["mime_type"] == "text/plain"
