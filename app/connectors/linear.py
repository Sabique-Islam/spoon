import asyncio
import logging
from collections.abc import Callable
from typing import Any

import httpx

from app.config import get_settings
from app.connectors.base import SyncResult
from app.models import Document
from app.supermemory.ingest import upload_documents

logger = logging.getLogger("spoon")

LINEAR_API_URL = "https://api.linear.app/graphql"
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
MAX_RETRIES = 3
PAGE_SIZE = 50

ISSUES_QUERY = """
query Issues($first: Int!, $after: String) {
  issues(first: $first, after: $after, orderBy: updatedAt) {
    nodes {
      id
      identifier
      title
      description
      url
      priority
      createdAt
      updatedAt
      state { name }
      team { name key }
      assignee { name email }
      labels { nodes { name } }
      project { id name }
    }
    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
"""

PROJECTS_QUERY = """
query Projects($first: Int!, $after: String) {
  projects(first: $first, after: $after, orderBy: updatedAt) {
    nodes {
      id
      name
      description
      content
      url
      slugId
      state
      progress
      startDate
      targetDate
      createdAt
      updatedAt
      lead { name }
      status { name }
      teams { nodes { name key } }
    }
    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
"""


def _truncate(content: str) -> str:
    return content[: get_settings().max_content_length]


def issue_to_document(issue: dict[str, Any]) -> Document:
    labels = [label["name"] for label in issue.get("labels", {}).get("nodes", [])]
    state = (issue.get("state") or {}).get("name")
    team = issue.get("team") or {}
    assignee = issue.get("assignee") or {}
    project = issue.get("project") or {}

    content_parts = []
    if issue.get("description"):
        content_parts.append(issue["description"])

    details = [
        f"Type: Issue",
        f"Identifier: {issue.get('identifier', '')}",
        f"State: {state or 'Unknown'}",
        f"Team: {team.get('name') or team.get('key') or 'Unknown'}",
        f"Priority: {issue.get('priority', 'None')}",
    ]
    if project.get("name"):
        details.append(f"Project: {project['name']}")
    if assignee.get("name"):
        details.append(f"Assignee: {assignee['name']}")
    if labels:
        details.append(f"Labels: {', '.join(labels)}")

    content = _truncate("\n\n".join(content_parts + ["\n".join(details)]))

    identifier = issue.get("identifier", issue["id"])
    title = issue.get("title") or "Untitled"

    return Document(
        id=f"linear-issue-{issue['id']}",
        source="linear",
        title=f"{identifier}: {title}",
        content=content.strip(),
        url=issue.get("url") or f"https://linear.app/issue/{identifier}",
        metadata={
            "object_type": "issue",
            "issue_id": issue["id"],
            "identifier": identifier,
            "state": state,
            "team": team.get("name") or team.get("key"),
            "project": project.get("name"),
            "assignee": assignee.get("name"),
            "labels": ", ".join(labels) if labels else None,
            "priority": issue.get("priority"),
            "created_at": issue.get("createdAt"),
            "updated_at": issue.get("updatedAt"),
        },
    )


def project_to_document(project: dict[str, Any]) -> Document:
    teams = [
        team.get("name") or team.get("key")
        for team in project.get("teams", {}).get("nodes", [])
    ]
    lead = (project.get("lead") or {}).get("name")
    status = (project.get("status") or {}).get("name")

    content_parts = []
    if project.get("content"):
        content_parts.append(project["content"])
    elif project.get("description"):
        content_parts.append(project["description"])

    details = [
        "Type: Project",
        f"State: {project.get('state') or 'Unknown'}",
    ]
    if status:
        details.append(f"Status: {status}")
    if teams:
        details.append(f"Teams: {', '.join(teams)}")
    if lead:
        details.append(f"Lead: {lead}")
    if project.get("progress") is not None:
        details.append(f"Progress: {round(project['progress'] * 100)}%")
    if project.get("startDate"):
        details.append(f"Start date: {project['startDate']}")
    if project.get("targetDate"):
        details.append(f"Target date: {project['targetDate']}")

    content = _truncate("\n\n".join(content_parts + ["\n".join(details)]))

    name = project.get("name") or "Untitled Project"
    slug = project.get("slugId") or project["id"]

    return Document(
        id=f"linear-project-{project['id']}",
        source="linear",
        title=f"Project: {name}",
        content=content.strip(),
        url=project.get("url") or f"https://linear.app/project/{slug}",
        metadata={
            "object_type": "project",
            "project_id": project["id"],
            "slug_id": project.get("slugId"),
            "state": project.get("state"),
            "status": status,
            "teams": ", ".join(teams) if teams else None,
            "lead": lead,
            "progress": project.get("progress"),
            "created_at": project.get("createdAt"),
            "updated_at": project.get("updatedAt"),
        },
    )


class LinearConnector:
    provider = "linear"

    def is_authenticated(self) -> bool:
        return bool(get_settings().linear_api_key)

    async def _graphql(
        self,
        client: httpx.AsyncClient,
        query: str,
        variables: dict[str, Any],
    ) -> dict[str, Any]:
        settings = get_settings()
        if not settings.linear_api_key:
            raise ValueError("Linear is not authenticated. Set SPOON_LINEAR_API_KEY.")

        headers = {
            "Authorization": settings.linear_api_key,
            "Content-Type": "application/json",
        }

        last_response: httpx.Response | None = None
        for attempt in range(MAX_RETRIES):
            response = await client.post(
                LINEAR_API_URL,
                json={"query": query, "variables": variables},
                headers=headers,
                timeout=30.0,
            )
            last_response = response
            if response.status_code not in RETRYABLE_STATUS:
                break
            await asyncio.sleep(2**attempt)

        assert last_response is not None
        if last_response.status_code == 401:
            raise httpx.HTTPStatusError(
                "Unauthorized", request=last_response.request, response=last_response
            )
        last_response.raise_for_status()

        payload = last_response.json()
        if payload.get("errors"):
            messages = "; ".join(
                err.get("message", str(err)) for err in payload["errors"]
            )
            raise ValueError(f"Linear GraphQL error: {messages}")

        return payload.get("data", {})

    async def _fetch_paginated(
        self,
        client: httpx.AsyncClient,
        query: str,
        connection_name: str,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        cursor: str | None = None

        while True:
            variables: dict[str, Any] = {"first": PAGE_SIZE}
            if cursor:
                variables["after"] = cursor

            data = await self._graphql(client, query, variables)
            connection = data.get(connection_name) or {}
            items.extend(connection.get("nodes", []))

            page_info = connection.get("pageInfo") or {}
            if not page_info.get("hasNextPage"):
                break
            cursor = page_info.get("endCursor")

        return items

    async def sync(self) -> SyncResult:
        result = SyncResult()

        if not self.is_authenticated():
            result.errors.append(
                "Linear is not authenticated. Set SPOON_LINEAR_API_KEY."
            )
            return result

        documents: list[Document] = []

        async with httpx.AsyncClient() as client:
            fetchers: list[tuple[str, str, str, Callable[[dict[str, Any]], Document]]] = [
                ("issues", ISSUES_QUERY, "issues", issue_to_document),
                ("projects", PROJECTS_QUERY, "projects", project_to_document),
            ]

            for label, query, connection, to_document in fetchers:
                try:
                    items = await self._fetch_paginated(client, query, connection)
                    documents.extend(
                        to_document(item) for item in items if item.get("id")
                    )
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 401:
                        result.errors.append(
                            "Linear API key is invalid. Check SPOON_LINEAR_API_KEY."
                        )
                        return result
                    result.errors.append(f"Failed to fetch Linear {label}: {exc}")
                except (httpx.HTTPError, ValueError) as exc:
                    result.errors.append(f"Failed to fetch Linear {label}: {exc}")

            if not documents and result.errors:
                return result

            try:
                upload_documents(documents)
                result.documents_processed = len(documents)
            except Exception as exc:
                logger.exception("Supermemory upload failed")
                result.errors.append(f"Failed to upload documents: {exc}")

        return result
