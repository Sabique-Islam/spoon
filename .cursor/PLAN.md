# Spoon V1

## Goal

Connect supported services, ingest their data into Supermemory, and expose a single search endpoint.

## Supported Providers

* Gmail
* Outlook
* Slack
* Notion
* Linear
* Google Drive

## Out of Scope

* LLMs
* Chat
* Elasticsearch
* Database
* Background jobs
* Scheduled sync
* User accounts
* Permissions
* Analytics
* Caching

## Flow

```text
Authenticate
    ↓
Fetch provider data
    ↓
Normalize
    ↓
Upload to Supermemory
    ↓
Search through Supermemory
```

## Data Model

All providers are converted into a common document format.

Fields:

* id
* source
* title
* content
* url
* metadata

## API -> /api/v1

### Health

`GET /health`

Returns service status.

### Providers

`GET /providers`

Returns supported providers.

### OAuth

`GET /auth/{provider}`

Starts the OAuth flow.

`GET /auth/{provider}/callback`

Handles the OAuth callback.

### Sync

`POST /sync/{provider}`

Syncs a single provider.

`POST /sync/all`

Syncs every connected provider.

### Search

`POST /search`

Searches documents through the Supermemory API.

## Sync Process

For every provider:

1. Authenticate.
2. Fetch data.
3. Normalize into the common document model.
4. Upload to Supermemory.
5. Return the number of documents processed and any errors.

## Search Process

1. Receive query.
2. Send query to Supermemory.
3. Return results without modification.

## Error Handling

* Return JSON errors.
* Handle expired OAuth tokens.
* Retry transient HTTP failures.
* Do not expose internal errors.

## Logging

Log:

* Incoming requests
* Provider being synced
* Number of documents uploaded
* Sync duration
* Search duration
* Errors

## Testing

Verify:

* Health endpoint
* OAuth flow
* Document normalization
* Sync pipeline
* Supermemory upload
* Search endpoint
