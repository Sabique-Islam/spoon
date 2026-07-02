# `slack.py` — Slack Workspace Sync

## Purpose

`slack.py` is the largest Spoon connector. It syncs a **Slack workspace** into many `Document` objects: team info, users, files, emoji, user groups, and per-channel bundles (topic, purpose, pins, bookmarks, members, messages with threads).

Authentication uses **Slack OAuth** or a **bot token** (`SPOON_SLACK_BOT_TOKEN`).

## Architecture Role

```
Slack OAuth / Bot token
        │
        ▼
SlackConnector.sync()
        │
        ├── Workspace metadata (team, users, files, emoji, usergroups)
        └── Per channel (capped by max_slack_channels):
                ├── messages + thread replies
                ├── pins, bookmarks, members
                └── channel_to_document()
        │
        ▼
upload_document_batch(all documents, result)
        │
        ▼
Supermemory
```

| Document type | ID prefix | Source function |
|---------------|-----------|-----------------|
| Team | `slack-team-` | `team_to_document` |
| User | `slack-user-` | `user_to_document` |
| File | `slack-file-` | `file_to_document` |
| Emoji | `slack-emoji` | `emoji_to_document` |
| User group | `slack-usergroup-` | `usergroup_to_document` |
| Channel | `slack-channel-` | `channel_to_document` |

## Dependencies

| Import | Module | Usage |
|--------|--------|-------|
| `asyncio`, `logging` | stdlib | Rate limits, errors |
| `datetime` | stdlib | Timestamp formatting |
| `httpx` | third-party | Slack Web API (POST form) |
| `get_slack_access_token` | `app.auth.slack_oauth` | Token resolution |
| `get_provider_token` | `app.auth.store` | OAuth check |
| `get_settings` | `app.config` | Channel/message limits, bot token |
| `SyncResult`, `upload_document_batch` | `app.connectors.base` | Quota-aware upload |
| `Document` | `app.models` | Output model |
| `upload_documents` | `app.supermemory.ingest` | Imported but batch uses `upload_document_batch` |

## Line-Range Reference

### Module header and constants (1–31)

| Lines | Section | Description |
|-------|---------|-------------|
| 1–4 | Imports | asyncio, logging, datetime, typing |
| 6 | httpx | HTTP client |
| 8–13 | App imports | auth, config, base, models, ingest |
| 15 | Logger | `"spoon"` |
| 17 | `SLACK_API_BASE` | `https://slack.com/api` |
| 18–20 | Retry constants | Status codes, retries, page size 200 |
| 22–31 | `SKIPPABLE_ERRORS` | API errors to skip quietly (scope, channel, auth) |

### Text helpers (34–79)

| Lines | Function | Description |
|-------|----------|-------------|
| 34–35 | `_truncate` | Slice to max_content_length |
| 38–44 | `_format_timestamp` | Unix ts → ISO local string |
| 47–56 | `_user_display_name` | Profile display/real/name fallback |
| 59–60 | `_resolve_user_name` | user_id → name from map |
| 63–71 | `_channel_title` | DM/Group DM/channel title with icons |
| 74–78 | `_channel_url` | Workspace archive URL or app_redirect |

### Message and entity normalizers (81–269)

| Lines | Function | Description |
|-------|----------|-------------|
| 81–119 | `message_to_text` | User, text, attachments, blocks, reactions → line |
| 122–143 | `team_to_document` | Workspace metadata Document |
| 146–175 | `user_to_document` | Member profile Document (skip deleted) |
| 178–209 | `usergroup_to_document` | User group + members Document |
| 212–251 | `file_to_document` | Slack file metadata Document |
| 254–269 | `emoji_to_document` | Custom emoji name→URL list Document |

#### `message_to_text` detail (81–119)

| Lines | Logic |
|-------|-------|
| 82–84 | Resolve user/bot id to display name |
| 84 | Base message text |
| 86–94 | Attachment text/fallback append |
| 96–104 | Block kit text elements append |
| 106–107 | Empty → return "" |
| 109 | Format `[name] (time): text` |
| 111–117 | Optional reactions suffix |
| 119 | Return line |

#### `team_to_document` detail (122–143)

| Lines | Logic |
|-------|-------|
| 123–125 | Require team id |
| 127–132 | Name, domain, email domain, icon lines |
| 133 | Truncate non-empty lines |
| 134–142 | Document with workspace URL |

#### `user_to_document` detail (146–175)

| Lines | Logic |
|-------|-------|
| 147–149 | Skip missing id or deleted |
| 151–163 | Profile field lines |
| 164–166 | Skip if no content |
| 168–175 | Document with app_redirect URL |

#### `usergroup_to_document` detail (178–209)

| Lines | Logic |
|-------|-------|
| 181–183 | Require group id |
| 185–193 | Handle, name, description, members |
| 195–200 | Truncate; admin URL if domain |
| 202–209 | Document |

#### `file_to_document` detail (212–251)

| Lines | Logic |
|-------|-------|
| 213–215 | Require file id |
| 217–227 | Metadata lines + uploader |
| 228–235 | initial_comment, preview, plain_text |
| 237–250 | Document with permalink |

#### `emoji_to_document` detail (254–269)

| Lines | Logic |
|-------|-------|
| 255–256 | Empty dict → None |
| 258–259 | Sorted `:name: url` lines |
| 260 | Emoji settings URL |
| 262–269 | Single doc id `slack-emoji` |

### Pin, bookmark, channel builders (272–365)

| Lines | Function | Description |
|-------|----------|-------------|
| 272–281 | `pin_to_text` | Pinned message or file summary |
| 284–289 | `bookmark_to_text` | Bookmark title/link/emoji |
| 292–365 | `channel_to_document` | Full channel Document assembly |

#### `pin_to_text` (272–281)

| Lines | Logic |
|-------|-------|
| 273–277 | type=message → message_to_text with prefix |
| 278–280 | type=file → file name |
| 281 | Default "" |

#### `bookmark_to_text` (284–289)

| Lines | Logic |
|-------|-------|
| 285–288 | title/link/emoji formatting |
| 289 | Return formatted string |

#### `channel_to_document` (292–365)

| Lines | Logic |
|-------|-------|
| 302–303 | channel_id, sections list |
| 305–312 | Topic, purpose, members |
| 314–318 | Pinned items section |
| 320–324 | Bookmarks section |
| 326–339 | Messages loop (thread_reply vs normal) |
| 341–342 | Skip if no sections |
| 344 | Truncate joined sections |
| 346–365 | Document with rich metadata |

**Message loop rules (327–337):**

| Condition | Behavior |
|-----------|----------|
| `subtype == thread_reply` | Append raw text only |
| Other subtype (not bot_message) | Skip |
| Else | `message_to_text` |

### `SlackConnector` — auth and API layer (368–431)

| Lines | Member | Description |
|-------|--------|-------------|
| 369 | `provider` | `"slack"` |
| 371–374 | `is_authenticated` | OAuth token or bot token setting |
| 376–382 | `_resolve_token` | get_slack_access_token |
| 384–416 | `_api_call` | POST method, retries, rate limits |
| 418–431 | `_api_call_optional` | Swallows SKIPPABLE_ERRORS |

#### `_api_call` detail (384–416)

| Lines | Logic |
|-------|-------|
| 391–392 | Bearer auth, URL |
| 394–400 | Retry on RETRYABLE_STATUS + Retry-After |
| 402–407 | ok → return data |
| 409–411 | ratelimited → backoff |
| 413 | Raise ValueError with error code |
| 415–416 | Exhaust retries |

### Pagination and fetch helpers (433–637)

| Lines | Member | Description |
|-------|--------|-------------|
| 433–467 | `_paginate` | Cursor pagination generic helper |
| 469–474 | `_fetch_users` | users.list → members + name map |
| 476–486 | `_fetch_channels` | conversations.list all types |
| 488–537 | `_fetch_channel_messages` | History + threads + cap |
| 539–554 | `_fetch_channel_members` | conversations.members |
| 556–560 | `_fetch_pins` | pins.list optional |
| 562–568 | `_fetch_bookmarks` | bookmarks.list optional |
| 570–574 | `_fetch_team` | team.info |
| 576–582 | `_fetch_usergroups` | usergroups.list with users |
| 584–607 | `_fetch_files` | files.list page-based |
| 609–631 | `_fetch_remote_files` | files.remote.list cursor |
| 633–637 | `_fetch_emoji` | emoji.list optional |

#### `_paginate` (433–467)

| Lines | Logic |
|-------|-------|
| 443–445 | optional vs required call |
| 447–451 | limit + cursor params |
| 453–455 | Break if optional returns None |
| 457–461 | dict result → single item; else extend list |
| 463–465 | next_cursor loop |

#### `_fetch_channel_messages` (488–537)

| Lines | Logic |
|-------|-------|
| 495–501 | conversations.history paginated |
| 502 | Reverse chronological → ascending |
| 503–505 | Cap to max_slack_messages_per_channel (keep newest) |
| 507–511 | Find threaded parents |
| 512–530 | Fetch replies, indent with ↳ |
| 532–537 | Expand messages + synthetic thread_reply entries |

#### `_fetch_files` (584–607)

| Lines | Logic |
|-------|-------|
| 587–588 | Page counter |
| 590–599 | files.list optional |
| 601 | Extend files |
| 602–605 | Break when page >= total pages |

#### `_fetch_remote_files` (609–631)

| Lines | Logic |
|-------|-------|
| 612–618 | Cursor params |
| 620–624 | Optional API call |
| 626–629 | Cursor pagination |

### `sync` orchestration (639–743)

| Lines | Section | Description |
|-------|---------|-------------|
| 639–646 | Token resolve | ValueError → error |
| 648 | documents list | Accumulator |
| 650–669 | Initial fetch block | team, users, channels, groups, files, emoji |
| 659–669 | Error handling | 401 invalid token; other HTTP/ValueError |
| 671 | team_domain | For URL building |
| 673–676 | Team document | Append if valid |
| 678–681 | User documents | All members |
| 683–691 | File documents | Dedupe by file id |
| 693–695 | Emoji document | Single aggregate doc |
| 697–702 | User group documents | With member names |
| 704–735 | Channel loop | Capped by max_slack_channels |
| 708–726 | Per channel | messages, pins, bookmarks, members → doc |
| 729–735 | Channel errors | Skip SKIPPABLE; else add_error |
| 737–741 | Upload | upload_document_batch + exception handler |
| 743 | Return | SyncResult |

## Functions and Classes Summary

### Constants

| Name | Value |
|------|-------|
| `SLACK_API_BASE` | Slack Web API root |
| `PAGE_SIZE` | 200 |
| `MAX_RETRIES` | 3 |
| `SKIPPABLE_ERRORS` | 7 error codes for graceful skip |

### Module-level functions (19)

All functions listed in line-range tables above are public module API except `_`-prefixed helpers.

### `SlackConnector` methods (18)

| Method | Async | Description |
|--------|-------|-------------|
| `is_authenticated` | No | Token available |
| `_resolve_token` | Yes | Get bearer token |
| `_api_call` | Yes | Required Slack method |
| `_api_call_optional` | Yes | Skip on scope errors |
| `_paginate` | Yes | Generic cursor pagination |
| `_fetch_users` | Yes | Members + id→name map |
| `_fetch_channels` | Yes | All conversation types |
| `_fetch_channel_messages` | Yes | History + threads |
| `_fetch_channel_members` | Yes | Member display names |
| `_fetch_pins` | Yes | Optional |
| `_fetch_bookmarks` | Yes | Optional |
| `_fetch_team` | Yes | Workspace info |
| `_fetch_usergroups` | Yes | Optional |
| `_fetch_files` | Yes | Page pagination |
| `_fetch_remote_files` | Yes | Cursor pagination |
| `_fetch_emoji` | Yes | Optional |
| `sync` | Yes | Full workspace sync |

## Tradeoffs

### Pros

| Benefit | Detail |
|---------|--------|
| Rich workspace snapshot | Users, files, channels in one sync |
| Graceful degradation | Optional APIs skip missing scopes |
| Thread expansion | Replies inlined under parents |
| Channel document bundling | Searchable channel context in one doc |
| Quota-aware upload | `upload_document_batch` at end |
| Rate limit handling | Retry-After + ratelimited backoff |

### Cons

| Limitation | Detail |
|------------|--------|
| High API volume | Channels × (history + threads + pins + …) |
| Memory | All documents built before upload |
| Channel cap | Only first N channels (500 default) |
| Message cap | 2000 per channel — older messages dropped |
| Block kit partial | Only simple text blocks extracted |
| Single emoji doc | All emoji in one document |

### Alternatives

| Alternative | When |
|-------------|------|
| Event API incremental | Real-time vs batch |
| One doc per message | Finer-grained search |
| Slack export ZIP | Offline bulk import |
| Enterprise Grid scoping | Multi-workspace |

## Security and Resource Notes

| Topic | Detail |
|-------|--------|
| Bot token scopes | Many methods need explicit scopes; others skip |
| PII | User emails, DMs, file URLs in Supermemory |
| SKIPPABLE auth errors | Invalid token may skip quietly in optional calls |
| API volume | Rate limits — PAGE_SIZE 200, retries |
| Settings | `max_slack_channels`, `max_slack_messages_per_channel` |
| Private channels | Require bot invited + scopes |
| File URLs | May include `url_private` (token-gated at Slack) |

## Extension Guide

### Add a new Slack resource (e.g. canvases)

1. Add `_fetch_canvases` using `_paginate` or `_api_call_optional`.
2. Add `canvas_to_document(canvas) -> Document | None`.
3. Append in `sync()` before channel loop.
4. Add new error codes to `SKIPPABLE_ERRORS` if scope-gated.

### One document per message

Replace channel bundling with a loop that calls `upload_document_batch` per message — increases document count and API alignment with Gmail pattern.

### Filter channels

Before channel loop:

```python
channels = [c for c in channels if not c.get("is_archived")]
```

### Improve Block Kit support

Extend `message_to_text` to walk nested block elements (sections, fields, context).

### Testing

Pure functions (`message_to_text`, `channel_to_document`, etc.) accept fixture dicts.

See `tests/test_sync_slack.py` for integration patterns.

## Configuration Reference

| Setting | Default | Effect |
|---------|---------|--------|
| `slack_bot_token` | None | Fallback auth |
| `max_content_length` | 100,000 | Truncation |
| `max_documents_per_sync` | 5000 | Upload batch limit |
| `max_slack_channels` | 500 | Channels processed |
| `max_slack_messages_per_channel` | 2000 | Messages per channel |
