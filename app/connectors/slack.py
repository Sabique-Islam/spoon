import asyncio
import logging
from datetime import datetime
from typing import Any

import httpx

from app.auth.slack_oauth import get_slack_access_token
from app.auth.store import get_provider_token
from app.config import get_settings
from app.connectors.base import SyncResult
from app.models import Document
from app.supermemory.ingest import upload_documents

logger = logging.getLogger("spoon")

SLACK_API_BASE = "https://slack.com/api"
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
MAX_RETRIES = 3
PAGE_SIZE = 200


def _truncate(content: str) -> str:
    return content[: get_settings().max_content_length]


def _format_timestamp(ts: str | float | None) -> str:
    if ts is None:
        return "unknown time"
    try:
        return datetime.fromtimestamp(float(ts)).isoformat(sep=" ", timespec="seconds")
    except (TypeError, ValueError, OSError):
        return str(ts)


def message_to_text(message: dict[str, Any], user_names: dict[str, str]) -> str:
    user_id = message.get("user") or message.get("bot_id") or "unknown"
    name = user_names.get(str(user_id), str(user_id))
    text = (message.get("text") or "").strip()

    attachments = message.get("attachments") or []
    attachment_texts = [
        part.strip()
        for attachment in attachments
        for part in [attachment.get("text") or "", attachment.get("fallback") or ""]
        if part and part.strip()
    ]
    if attachment_texts:
        text = "\n".join([text] + attachment_texts) if text else "\n".join(attachment_texts)

    if not text:
        return ""

    return f"[{name}] ({_format_timestamp(message.get('ts'))}): {text}"


def channel_to_document(
    channel: dict[str, Any],
    messages: list[dict[str, Any]],
    user_names: dict[str, str],
    team_domain: str | None,
) -> Document | None:
    channel_id = channel["id"]
    name = channel.get("name") or channel.get("id")
    is_im = channel.get("is_im")
    is_mpim = channel.get("is_mpim")

    if is_im:
        title = f"DM: {name}"
    elif is_mpim:
        title = f"Group DM: {name}"
    else:
        title = f"#{name}"

    lines = [
        message_to_text(message, user_names)
        for message in messages
        if not message.get("subtype") or message.get("subtype") == "bot_message"
    ]
    lines = [line for line in lines if line]
    if not lines:
        return None

    content = _truncate("\n".join(lines))
    if team_domain and not is_im:
        url = f"https://{team_domain}.slack.com/archives/{channel_id}"
    else:
        url = f"https://slack.com/app_redirect?channel={channel_id}"

    return Document(
        id=f"slack-channel-{channel_id}",
        source="slack",
        title=title,
        content=content,
        url=url,
        metadata={
            "object_type": "channel",
            "channel_id": channel_id,
            "channel_name": name,
            "message_count": len(lines),
            "is_private": channel.get("is_private"),
            "is_im": is_im,
            "is_mpim": is_mpim,
        },
    )


class SlackConnector:
    provider = "slack"

    def is_authenticated(self) -> bool:
        if get_provider_token("slack"):
            return True
        return bool(get_settings().slack_bot_token)

    async def _resolve_token(self) -> str:
        token = await get_slack_access_token()
        if not token:
            raise ValueError(
                "Slack is not authenticated. Visit /api/v1/auth/slack or set SPOON_SLACK_BOT_TOKEN."
            )
        return token

    async def _api_call(
        self,
        client: httpx.AsyncClient,
        token: str,
        method: str,
        **params: Any,
    ) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{SLACK_API_BASE}/{method}"

        last_data: dict[str, Any] | None = None
        for attempt in range(MAX_RETRIES):
            response = await client.post(url, headers=headers, data=params, timeout=30.0)
            if response.status_code in RETRYABLE_STATUS:
                retry_after = int(response.headers.get("Retry-After", 2**attempt))
                await asyncio.sleep(retry_after)
                continue

            response.raise_for_status()
            data = response.json()
            last_data = data

            if data.get("ok"):
                return data

            if data.get("error") == "ratelimited":
                await asyncio.sleep(2**attempt)
                continue

            raise ValueError(data.get("error", f"Slack API error for {method}"))

        assert last_data is not None
        raise ValueError(last_data.get("error", f"Slack API error for {method}"))

    async def _fetch_user_names(
        self, client: httpx.AsyncClient, token: str
    ) -> dict[str, str]:
        names: dict[str, str] = {}
        cursor: str | None = None

        while True:
            params: dict[str, Any] = {"limit": PAGE_SIZE}
            if cursor:
                params["cursor"] = cursor

            data = await self._api_call(client, token, "users.list", **params)
            for member in data.get("members", []):
                user_id = member.get("id")
                if not user_id:
                    continue
                profile = member.get("profile") or {}
                display = (
                    profile.get("display_name")
                    or profile.get("real_name")
                    or member.get("name")
                    or user_id
                )
                names[user_id] = display

            cursor = (data.get("response_metadata") or {}).get("next_cursor")
            if not cursor:
                break

        return names

    async def _fetch_channels(
        self, client: httpx.AsyncClient, token: str
    ) -> list[dict[str, Any]]:
        channels: list[dict[str, Any]] = []
        cursor: str | None = None

        while True:
            params: dict[str, Any] = {
                "types": "public_channel,private_channel,im,mpim",
                "limit": PAGE_SIZE,
                "exclude_archived": "true",
            }
            if cursor:
                params["cursor"] = cursor

            data = await self._api_call(client, token, "conversations.list", **params)
            channels.extend(data.get("channels", []))

            cursor = (data.get("response_metadata") or {}).get("next_cursor")
            if not cursor:
                break

        return channels

    async def _fetch_channel_messages(
        self,
        client: httpx.AsyncClient,
        token: str,
        channel_id: str,
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        cursor: str | None = None

        while True:
            params: dict[str, Any] = {"channel": channel_id, "limit": PAGE_SIZE}
            if cursor:
                params["cursor"] = cursor

            data = await self._api_call(client, token, "conversations.history", **params)
            messages.extend(data.get("messages", []))

            cursor = (data.get("response_metadata") or {}).get("next_cursor")
            if not cursor:
                break

        messages.reverse()
        return messages

    async def _fetch_team_domain(
        self, client: httpx.AsyncClient, token: str
    ) -> str | None:
        try:
            data = await self._api_call(client, token, "team.info")
            return (data.get("team") or {}).get("domain")
        except ValueError:
            return None

    async def sync(self) -> SyncResult:
        result = SyncResult()

        try:
            token = await self._resolve_token()
        except ValueError as exc:
            result.errors.append(str(exc))
            return result

        documents: list[Document] = []

        async with httpx.AsyncClient() as client:
            try:
                user_names = await self._fetch_user_names(client, token)
                channels = await self._fetch_channels(client, token)
                team_domain = await self._fetch_team_domain(client, token)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 401:
                    result.errors.append(
                        "Slack token is invalid. Re-authenticate at /api/v1/auth/slack."
                    )
                else:
                    result.errors.append(f"Failed to fetch Slack workspace data: {exc}")
                return result
            except (httpx.HTTPError, ValueError) as exc:
                result.errors.append(f"Failed to fetch Slack workspace data: {exc}")
                return result

            for channel in channels:
                channel_id = channel.get("id")
                if not channel_id:
                    continue
                channel_name = channel.get("name") or channel_id
                try:
                    messages = await self._fetch_channel_messages(
                        client, token, channel_id
                    )
                    doc = channel_to_document(channel, messages, user_names, team_domain)
                    if doc:
                        documents.append(doc)
                except (httpx.HTTPError, ValueError) as exc:
                    result.errors.append(
                        f"Failed to fetch messages for {channel_name}: {exc}"
                    )

            try:
                upload_documents(documents)
                result.documents_processed = len(documents)
            except Exception as exc:
                logger.exception("Supermemory upload failed")
                result.errors.append(f"Failed to upload documents: {exc}")

        return result
