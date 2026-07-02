from app.connectors.linear import issue_to_document, project_to_document


def test_issue_to_document():
    issue = {
        "id": "issue-uuid-1",
        "identifier": "ENG-42",
        "title": "Fix login bug",
        "description": "Users cannot log in with SSO.",
        "url": "https://linear.app/acme/issue/ENG-42",
        "priority": 2,
        "createdAt": "2024-01-01T00:00:00.000Z",
        "updatedAt": "2024-01-02T00:00:00.000Z",
        "state": {"name": "In Progress"},
        "team": {"name": "Engineering", "key": "ENG"},
        "assignee": {"name": "Jane Doe", "email": "jane@example.com"},
        "labels": {"nodes": [{"name": "bug"}, {"name": "auth"}]},
    }

    doc = issue_to_document(issue)
    assert doc.id == "linear-issue-issue-uuid-1"
    assert doc.source == "linear"
    assert doc.title == "ENG-42: Fix login bug"
    assert "Users cannot log in with SSO." in doc.content
    assert "State: In Progress" in doc.content
    assert "Labels: bug, auth" in doc.content
    assert doc.url == "https://linear.app/acme/issue/ENG-42"
    assert doc.metadata["identifier"] == "ENG-42"
    assert doc.metadata["team"] == "Engineering"


def test_project_to_document():
    project = {
        "id": "project-uuid-1",
        "name": "Q3 Roadmap",
        "description": "Short summary",
        "content": "Full project brief with goals and milestones.",
        "url": "https://linear.app/acme/project/q3-roadmap-abc123",
        "slugId": "q3-roadmap-abc123",
        "state": "started",
        "progress": 0.45,
        "startDate": "2024-07-01",
        "targetDate": "2024-09-30",
        "createdAt": "2024-06-01T00:00:00.000Z",
        "updatedAt": "2024-07-01T00:00:00.000Z",
        "lead": {"name": "Alex"},
        "status": {"name": "In Progress"},
        "teams": {"nodes": [{"name": "Engineering", "key": "ENG"}]},
    }

    doc = project_to_document(project)
    assert doc.id == "linear-project-project-uuid-1"
    assert doc.source == "linear"
    assert doc.title == "Project: Q3 Roadmap"
    assert "Full project brief" in doc.content
    assert "Type: Project" in doc.content
    assert "Lead: Alex" in doc.content
    assert doc.metadata["object_type"] == "project"

    issue = {
        "id": "issue-uuid-2",
        "identifier": "ENG-1",
        "title": "Empty issue",
    }
    doc = issue_to_document(issue)
    assert doc.title == "ENG-1: Empty issue"
    assert doc.source == "linear"
