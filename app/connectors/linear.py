import asyncio
import logging
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
    }
    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
"""


def issue_to_document(issue: dict[str, Any]) -> Document:
    settings = get_settings()
    labels = [label["name"] for label in issue.get("labels", {}).get("nodes", [])]
    state = (issue.get("state") or {}).get("name")
    team = issue.get("team") or {}
    assignee = issue.get("assignee") or {}

    content_parts = []
    if issue.get("description"):
        content_parts.append(issue["description"])

    details = [
        f"Identifier: {issue.get('identifier', '')}",
        f"State: {state or 'Unknown'}",
        f"Team: {team.get('name') or team.get('key') or 'Unknown'}",
        f"Priority: {issue.get('priority', 'None')}",
    ]
    if assignee.get("name"):
        details.append(f"Assignee: {assignee['name']}")
    if labels:
        details.append(f"Labels: {', '.join(labels)}")

    content = "\n\n".join(content_parts + ["\n".join(details)])
    content = content[: settings.max_content_length]

    identifier = issue.get("identifier", issue["id"])
    title = issue.get("title") or "Untitled"

    return Document(
        id=f"linear-{issue['id']}",
        source="linear",
        title=f"{identifier}: {title}",
        content=content.strip(),
        url=issue.get("url") or f"https://linear.app/issue/{identifier}",
        metadata={
            "issue_id": issue["id"],
            "identifier": identifier,
            "state": state,
            "team": team.get("name") or team.get("key"),
            "assignee": assignee.get("name"),
            "labels": ", ".join(labels) if labels else None,
            "priority": issue.get("priority"),
            "created_at": issue.get("createdAt"),
            "updated_at": issue.get("updatedAt"),
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

    async def _fetch_issues(self, client: httpx.AsyncClient) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        cursor: str | None = None

        while True:
            variables: dict[str, Any] = {"first": PAGE_SIZE}
            if cursor:
                variables["after"] = cursor

            data = await self._graphql(client, ISSUES_QUERY, variables)
            connection = data.get("issues") or {}
            issues.extend(connection.get("nodes", []))

            page_info = connection.get("pageInfo") or {}
            if not page_info.get("hasNextPage"):
                break
            cursor = page_info.get("endCursor")

        return issues

    async def sync(self) -> SyncResult:
        result = SyncResult()

        if not self.is_authenticated():
            result.errors.append(
                "Linear is not authenticated. Set SPOON_LINEAR_API_KEY."
            )
            return result

        async with httpx.AsyncClient() as client:
            try:
                issues = await self._fetch_issues(client)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 401:
                    result.errors.append(
                        "Linear API key is invalid. Check SPOON_LINEAR_API_KEY."
                    )
                else:
                    result.errors.append(f"Failed to fetch Linear issues: {exc}")
                return result
            except (httpx.HTTPError, ValueError) as exc:
                result.errors.append(f"Failed to fetch Linear issues: {exc}")
                return result

            documents = [issue_to_document(issue) for issue in issues if issue.get("id")]

            try:
                upload_documents(documents)
                result.documents_processed = len(documents)
            except Exception as exc:
                logger.exception("Supermemory upload failed")
                result.errors.append(f"Failed to upload documents: {exc}")

        return result
