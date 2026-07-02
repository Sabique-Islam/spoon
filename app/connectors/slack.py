import asyncio
import logging
from datetime import datetime
from typing import Any

import httpx

from app.auth.slack_oauth import get_slack_access_token
from app.auth.store import get_provider_token
from app.config import get_settings
from app.connectors.base import SyncResult, upload_document_batch
from app.models import Document
from app.supermemory.ingest import upload_documents

logger = logging.getLogger("spoon")

SLACK_API_BASE = "https://slack.com/api"
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
MAX_RETRIES = 3
PAGE_SIZE = 200

# Errors that mean this resource is unavailable for this token/channel — skip quietly.
SKIPPABLE_ERRORS = {
    "missing_scope",
    "not_in_channel",
    "channel_not_found",
    "method_not_supported_for_channel_type",
    "not_authed",
    "account_inactive",
    "invalid_auth",
}


def _truncate(content: str) -> str:
    return content[: get_settings().max_content_length]


def _format_timestamp(ts: str | float | None) -> str:
    if ts is None:
        return "unknown time"
    try:
        return datetime.fromtimestamp(float(ts)).isoformat(sep=" ", timespec="seconds")
    except (TypeError, ValueError, OSError):
        return str(ts)


def _user_display_name(member: dict[str, Any]) -> str:
    profile = member.get("profile") or {}
    return (
        profile.get("display_name")
        or profile.get("real_name")
        or member.get("real_name")
        or member.get("name")
        or member.get("id")
        or "unknown"
    )


def _resolve_user_name(user_id: str, user_names: dict[str, str]) -> str:
    return user_names.get(user_id, user_id)


def _channel_title(channel: dict[str, Any]) -> str:
    name = channel.get("name") or channel.get("id")
    if channel.get("is_im"):
        return f"DM: {name}"
    if channel.get("is_mpim"):
        return f"Group DM: {name}"
    prefix = "🔒 " if channel.get("is_private") else ""
    archived = " (archived)" if channel.get("is_archived") else ""
    return f"{prefix}#{name}{archived}"


def _channel_url(channel: dict[str, Any], team_domain: str | None) -> str:
    channel_id = channel["id"]
    if team_domain and not channel.get("is_im"):
        return f"https://{team_domain}.slack.com/archives/{channel_id}"
    return f"https://slack.com/app_redirect?channel={channel_id}"


def message_to_text(message: dict[str, Any], user_names: dict[str, str]) -> str:
    user_id = message.get("user") or message.get("bot_id") or "unknown"
    name = _resolve_user_name(str(user_id), user_names)
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

    blocks = message.get("blocks") or []
    block_texts = [
        element.get("text", "")
        for block in blocks
        for element in [block.get("text") or {}]
        if isinstance(element, dict) and element.get("text")
    ]
    if block_texts:
        text = "\n".join([text] + block_texts) if text else "\n".join(block_texts)

    if not text:
        return ""

    line = f"[{name}] ({_format_timestamp(message.get('ts'))}): {text}"

    reactions = message.get("reactions") or []
    if reactions:
        reaction_parts = [
            f":{reaction.get('name', '?')}: ({reaction.get('count', 0)})"
            for reaction in reactions
        ]
        line = f"{line} [reactions: {', '.join(reaction_parts)}]"

    return line


def team_to_document(team: dict[str, Any]) -> Document | None:
    team_id = team.get("id")
    if not team_id:
        return None

    lines = [
        f"Name: {team.get('name', '')}",
        f"Domain: {team.get('domain', '')}",
        f"Email domain: {team.get('email_domain', '')}",
        f"Icon: {team.get('icon', {}).get('image_132', '')}",
    ]
    content = _truncate("\n".join(line for line in lines if line.split(": ", 1)[-1]))
    domain = team.get("domain")

    return Document(
        id=f"slack-team-{team_id}",
        source="slack",
        title=f"Workspace: {team.get('name', team_id)}",
        content=content,
        url=f"https://{domain}.slack.com" if domain else "https://slack.com",
        metadata={"object_type": "team", "team_id": team_id},
    )


def user_to_document(member: dict[str, Any]) -> Document | None:
    user_id = member.get("id")
    if not user_id or member.get("deleted"):
        return None

    profile = member.get("profile") or {}
    lines = [
        f"Username: {member.get('name', '')}",
        f"Display name: {profile.get('display_name', '')}",
        f"Real name: {profile.get('real_name') or member.get('real_name', '')}",
        f"Title: {profile.get('title', '')}",
        f"Email: {profile.get('email', '')}",
        f"Phone: {profile.get('phone', '')}",
        f"Status: {profile.get('status_text', '')}",
        f"Timezone: {member.get('tz_label', '')} ({member.get('tz', '')})",
        f"Admin: {member.get('is_admin', False)}",
        f"Bot: {member.get('is_bot', False)}",
    ]
    content = _truncate("\n".join(line for line in lines if line.split(": ", 1)[-1]))
    if not content.strip():
        return None

    return Document(
        id=f"slack-user-{user_id}",
        source="slack",
        title=f"User: {_user_display_name(member)}",
        content=content,
        url=f"https://slack.com/app_redirect?team={member.get('team_id', '')}&user={user_id}",
        metadata={"object_type": "user", "user_id": user_id},
    )


def usergroup_to_document(
    group: dict[str, Any], member_names: list[str], team_domain: str | None
) -> Document | None:
    group_id = group.get("id")
    if not group_id:
        return None

    handle = group.get("handle") or group_id
    lines = [
        f"Handle: @{handle}",
        f"Name: {group.get('name', '')}",
        f"Description: {group.get('description', '')}",
        f"Member count: {group.get('user_count', len(member_names))}",
    ]
    if member_names:
        lines.append(f"Members: {', '.join(member_names)}")

    content = _truncate("\n".join(line for line in lines if line.split(": ", 1)[-1]))
    url = (
        f"https://{team_domain}.slack.com/admin/user_groups"
        if team_domain
        else "https://slack.com"
    )

    return Document(
        id=f"slack-usergroup-{group_id}",
        source="slack",
        title=f"User group: @{handle}",
        content=content,
        url=url,
        metadata={"object_type": "usergroup", "usergroup_id": group_id},
    )


def file_to_document(file_obj: dict[str, Any], user_names: dict[str, str]) -> Document | None:
    file_id = file_obj.get("id")
    if not file_id:
        return None

    uploader = file_obj.get("user")
    uploader_name = _resolve_user_name(uploader, user_names) if uploader else "unknown"
    lines = [
        f"Name: {file_obj.get('name') or file_obj.get('title', '')}",
        f"Title: {file_obj.get('title', '')}",
        f"Type: {file_obj.get('mimetype', file_obj.get('filetype', ''))}",
        f"Size: {file_obj.get('size', '')} bytes",
        f"Uploaded by: {uploader_name}",
        f"Created: {_format_timestamp(file_obj.get('created'))}",
        f"Permalink: {file_obj.get('permalink', '')}",
    ]
    for key in ("initial_comment", "preview", "plain_text"):
        value = file_obj.get(key)
        if isinstance(value, str) and value.strip():
            lines.append(f"{key.replace('_', ' ').title()}: {value.strip()}")
        elif isinstance(value, dict):
            preview_text = value.get("preview") or value.get("body") or value.get("text")
            if preview_text:
                lines.append(f"Preview: {preview_text}")

    content = _truncate("\n".join(line for line in lines if line.split(": ", 1)[-1]))
    url = file_obj.get("permalink") or file_obj.get("url_private") or "https://slack.com"

    return Document(
        id=f"slack-file-{file_id}",
        source="slack",
        title=f"File: {file_obj.get('name') or file_obj.get('title') or file_id}",
        content=content,
        url=url,
        metadata={
            "object_type": "file",
            "file_id": file_id,
            "mimetype": file_obj.get("mimetype"),
        },
    )


def emoji_to_document(emoji: dict[str, str], team_domain: str | None) -> Document | None:
    if not emoji:
        return None

    lines = [f":{name}: {url}" for name, url in sorted(emoji.items())]
    content = _truncate("\n".join(lines))
    url = f"https://{team_domain}.slack.com/customize/emoji" if team_domain else "https://slack.com"

    return Document(
        id="slack-emoji",
        source="slack",
        title="Custom emoji",
        content=content,
        url=url,
        metadata={"object_type": "emoji", "emoji_count": len(emoji)},
    )


def pin_to_text(item: dict[str, Any], user_names: dict[str, str]) -> str:
    if item.get("type") == "message":
        message = item.get("message") or {}
        text = message_to_text(message, user_names)
        if text:
            return f"Pinned message: {text}"
    if item.get("type") == "file":
        file_obj = item.get("file") or {}
        return f"Pinned file: {file_obj.get('name') or file_obj.get('title') or file_obj.get('id')}"
    return ""


def bookmark_to_text(bookmark: dict[str, Any]) -> str:
    title = bookmark.get("title") or bookmark.get("link") or "bookmark"
    link = bookmark.get("link") or ""
    emoji = bookmark.get("emoji") or ""
    prefix = f"{emoji} " if emoji else ""
    return f"{prefix}{title}: {link}".strip(": ")


def channel_to_document(
    channel: dict[str, Any],
    messages: list[dict[str, Any]],
    user_names: dict[str, str],
    team_domain: str | None,
    *,
    pins: list[dict[str, Any]] | None = None,
    bookmarks: list[dict[str, Any]] | None = None,
    members: list[str] | None = None,
) -> Document | None:
    channel_id = channel["id"]
    sections: list[str] = []

    topic = (channel.get("topic") or {}).get("value") or ""
    purpose = (channel.get("purpose") or {}).get("value") or ""
    if topic:
        sections.append(f"Topic: {topic}")
    if purpose:
        sections.append(f"Purpose: {purpose}")
    if members:
        sections.append(f"Members ({len(members)}): {', '.join(members)}")

    if pins:
        pin_lines = [pin_to_text(item, user_names) for item in pins]
        pin_lines = [line for line in pin_lines if line]
        if pin_lines:
            sections.append("Pinned:\n" + "\n".join(pin_lines))

    if bookmarks:
        bookmark_lines = [bookmark_to_text(bookmark) for bookmark in bookmarks]
        bookmark_lines = [line for line in bookmark_lines if line]
        if bookmark_lines:
            sections.append("Bookmarks:\n" + "\n".join(bookmark_lines))

    message_lines: list[str] = []
    for message in messages:
        if message.get("subtype") == "thread_reply":
            text = (message.get("text") or "").strip()
            if text:
                message_lines.append(text)
            continue
        if message.get("subtype") and message.get("subtype") != "bot_message":
            continue
        text = message_to_text(message, user_names)
        if text:
            message_lines.append(text)
    if message_lines:
        sections.append("Messages:\n" + "\n".join(message_lines))

    if not sections:
        return None

    content = _truncate("\n\n".join(sections))

    return Document(
        id=f"slack-channel-{channel_id}",
        source="slack",
        title=_channel_title(channel),
        content=content,
        url=_channel_url(channel, team_domain),
        metadata={
            "object_type": "channel",
            "channel_id": channel_id,
            "channel_name": channel.get("name"),
            "message_count": len(message_lines),
            "pin_count": len(pins or []),
            "bookmark_count": len(bookmarks or []),
            "member_count": len(members or []),
            "is_private": channel.get("is_private"),
            "is_im": channel.get("is_im"),
            "is_mpim": channel.get("is_mpim"),
            "is_archived": channel.get("is_archived"),
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

    async def _api_call_optional(
        self,
        client: httpx.AsyncClient,
        token: str,
        method: str,
        **params: Any,
    ) -> dict[str, Any] | None:
        try:
            return await self._api_call(client, token, method, **params)
        except ValueError as exc:
            if str(exc) in SKIPPABLE_ERRORS:
                logger.debug("Skipping Slack %s: %s", method, exc)
                return None
            raise

    async def _paginate(
        self,
        client: httpx.AsyncClient,
        token: str,
        method: str,
        result_key: str,
        *,
        optional: bool = False,
        **base_params: Any,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        cursor: str | None = None
        call = self._api_call_optional if optional else self._api_call

        while True:
            params = dict(base_params)
            params["limit"] = PAGE_SIZE
            if cursor:
                params["cursor"] = cursor

            data = await call(client, token, method, **params)
            if not data:
                break

            batch = data.get(result_key) or []
            if isinstance(batch, dict):
                items.append(batch)
                break
            items.extend(batch)

            cursor = (data.get("response_metadata") or {}).get("next_cursor")
            if not cursor:
                break

        return items

    async def _fetch_users(
        self, client: httpx.AsyncClient, token: str
    ) -> tuple[list[dict[str, Any]], dict[str, str]]:
        members = await self._paginate(client, token, "users.list", "members")
        names = {member["id"]: _user_display_name(member) for member in members if member.get("id")}
        return members, names

    async def _fetch_channels(
        self, client: httpx.AsyncClient, token: str
    ) -> list[dict[str, Any]]:
        return await self._paginate(
            client,
            token,
            "conversations.list",
            "channels",
            types="public_channel,private_channel,im,mpim",
            exclude_archived="false",
        )

    async def _fetch_channel_messages(
        self,
        client: httpx.AsyncClient,
        token: str,
        channel_id: str,
        user_names: dict[str, str],
    ) -> list[dict[str, Any]]:
        messages = await self._paginate(
            client,
            token,
            "conversations.history",
            "messages",
            channel=channel_id,
        )
        messages.reverse()
        max_messages = get_settings().max_slack_messages_per_channel
        if len(messages) > max_messages:
            messages = messages[-max_messages:]

        threaded_parents = [
            message
            for message in messages
            if message.get("reply_count", 0) > 0 and message.get("ts")
        ]
        for parent in threaded_parents:
            thread_ts = parent.get("thread_ts") or parent.get("ts")
            if not thread_ts:
                continue
            replies = await self._paginate(
                client,
                token,
                "conversations.replies",
                "messages",
                optional=True,
                channel=channel_id,
                ts=thread_ts,
            )
            for reply in replies:
                if reply.get("ts") == thread_ts:
                    continue
                reply_text = message_to_text(reply, user_names)
                if reply_text:
                    parent.setdefault("_thread_replies", []).append(f"  ↳ {reply_text}")

        expanded: list[dict[str, Any]] = []
        for message in messages:
            expanded.append(message)
            for reply_text in message.get("_thread_replies") or []:
                expanded.append({"text": reply_text, "subtype": "thread_reply"})
        return expanded

    async def _fetch_channel_members(
        self,
        client: httpx.AsyncClient,
        token: str,
        channel_id: str,
        user_names: dict[str, str],
    ) -> list[str]:
        member_ids = await self._paginate(
            client,
            token,
            "conversations.members",
            "members",
            optional=True,
            channel=channel_id,
        )
        return [_resolve_user_name(member_id, user_names) for member_id in member_ids]

    async def _fetch_pins(
        self, client: httpx.AsyncClient, token: str, channel_id: str
    ) -> list[dict[str, Any]]:
        data = await self._api_call_optional(client, token, "pins.list", channel=channel_id)
        return (data or {}).get("items") or []

    async def _fetch_bookmarks(
        self, client: httpx.AsyncClient, token: str, channel_id: str
    ) -> list[dict[str, Any]]:
        data = await self._api_call_optional(
            client, token, "bookmarks.list", channel_id=channel_id
        )
        return (data or {}).get("bookmarks") or []

    async def _fetch_team(
        self, client: httpx.AsyncClient, token: str
    ) -> dict[str, Any] | None:
        data = await self._api_call(client, token, "team.info")
        return data.get("team")

    async def _fetch_usergroups(
        self, client: httpx.AsyncClient, token: str
    ) -> list[dict[str, Any]]:
        data = await self._api_call_optional(
            client, token, "usergroups.list", include_users="true"
        )
        return (data or {}).get("usergroups") or []

    async def _fetch_files(
        self, client: httpx.AsyncClient, token: str
    ) -> list[dict[str, Any]]:
        files: list[dict[str, Any]] = []
        page = 1

        while True:
            data = await self._api_call_optional(
                client,
                token,
                "files.list",
                count=str(PAGE_SIZE),
                page=str(page),
            )
            if not data:
                break

            files.extend(data.get("files") or [])
            paging = data.get("paging") or {}
            if page >= paging.get("pages", page):
                break
            page += 1

        return files

    async def _fetch_remote_files(
        self, client: httpx.AsyncClient, token: str
    ) -> list[dict[str, Any]]:
        files: list[dict[str, Any]] = []
        cursor: str | None = None

        while True:
            params: dict[str, Any] = {"limit": PAGE_SIZE}
            if cursor:
                params["cursor"] = cursor

            data = await self._api_call_optional(
                client, token, "files.remote.list", **params
            )
            if not data:
                break

            files.extend(data.get("files") or [])
            cursor = (data.get("response_metadata") or {}).get("next_cursor")
            if not cursor:
                break

        return files

    async def _fetch_emoji(
        self, client: httpx.AsyncClient, token: str
    ) -> dict[str, str]:
        data = await self._api_call_optional(client, token, "emoji.list")
        return (data or {}).get("emoji") or {}

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
                team = await self._fetch_team(client, token)
                members, user_names = await self._fetch_users(client, token)
                channels = await self._fetch_channels(client, token)
                usergroups = await self._fetch_usergroups(client, token)
                files = await self._fetch_files(client, token)
                remote_files = await self._fetch_remote_files(client, token)
                emoji = await self._fetch_emoji(client, token)
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

            team_domain = (team or {}).get("domain")

            if team:
                doc = team_to_document(team)
                if doc:
                    documents.append(doc)

            for member in members:
                doc = user_to_document(member)
                if doc:
                    documents.append(doc)

            seen_file_ids: set[str] = set()
            for file_obj in files + remote_files:
                file_id = file_obj.get("id")
                if not file_id or file_id in seen_file_ids:
                    continue
                seen_file_ids.add(file_id)
                doc = file_to_document(file_obj, user_names)
                if doc:
                    documents.append(doc)

            emoji_doc = emoji_to_document(emoji, team_domain)
            if emoji_doc:
                documents.append(emoji_doc)

            for group in usergroups:
                users = group.get("users") or []
                member_names = [_resolve_user_name(user_id, user_names) for user_id in users]
                doc = usergroup_to_document(group, member_names, team_domain)
                if doc:
                    documents.append(doc)

            for channel in channels[: get_settings().max_slack_channels]:
                channel_id = channel.get("id")
                if not channel_id:
                    continue
                channel_name = channel.get("name") or channel_id
                try:
                    messages = await self._fetch_channel_messages(
                        client, token, channel_id, user_names
                    )
                    pins = await self._fetch_pins(client, token, channel_id)
                    bookmarks = await self._fetch_bookmarks(client, token, channel_id)
                    channel_members = await self._fetch_channel_members(
                        client, token, channel_id, user_names
                    )
                    doc = channel_to_document(
                        channel,
                        messages,
                        user_names,
                        team_domain,
                        pins=pins,
                        bookmarks=bookmarks,
                        members=channel_members or None,
                    )
                    if doc:
                        documents.append(doc)
                except (httpx.HTTPError, ValueError) as exc:
                    if str(exc) in SKIPPABLE_ERRORS:
                        logger.debug("Skipping channel %s: %s", channel_name, exc)
                        continue
                    result.errors.append(
                        f"Failed to fetch data for {channel_name}: {exc}"
                    )

            try:
                upload_document_batch(documents, result)
            except Exception as exc:
                logger.exception("Supermemory upload failed")
                result.add_error(f"Failed to upload documents: {exc}")

        return result
