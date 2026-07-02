# Spoon

Connect Knowledge Bases to Supermemory and search your documents.

> for teams, self host supermemory

## Run

```bash
make dev
```

## Security

Before exposing Spoon beyond localhost:

1. Set `SPOON_API_KEY` and pass it on every request (except `/health`):
   ```bash
   curl -H "X-API-Key: your-key" http://localhost:8000/api/v1/providers
   ```
2. Set `SPOON_TOKEN_ENCRYPTION_KEY` to encrypt OAuth tokens at rest
3. Set `SPOON_ENV=production` to disable `/docs`
4. Run behind a TLS reverse proxy
5. Restrict `.data/` directory permissions (tokens stored at `SPOON_TOKEN_STORE_PATH`)

Optional hardening:

- `SPOON_OAUTH_STATE_BACKEND=redis` + `SPOON_REDIS_URL` for multi-worker OAuth
- `SPOON_SYNC_SINCE_DAYS=90` to limit email sync window
- `SPOON_MAX_DOCUMENTS_PER_SYNC`, `SPOON_MAX_FILE_BYTES` for resource caps

Run security checks:

```bash
make security
```

## API

All endpoints are under `/api/v1`. When `SPOON_API_KEY` is set, include header `X-API-Key: ...` (or `Authorization: Bearer ...`).

### Health (no API key required)

```bash
curl http://localhost:8000/api/v1/health
```

### Providers

```bash
curl http://localhost:8000/api/v1/providers
```

### OAuth

```
GET /api/v1/auth/{provider}
GET /api/v1/auth/{provider}/callback
DELETE /api/v1/auth/{provider}   # disconnect
```

Providers: `notion`, `gdrive`, `slack`, `outlook`

### Sync

```bash
curl -X POST http://localhost:8000/api/v1/sync/{provider}
curl -X POST http://localhost:8000/api/v1/sync/all
```

Providers: `notion`, `linear`, `gdrive`, `gmail`, `outlook`, `slack`

### Search

```bash
curl -X POST http://localhost:8000/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{"query": "meeting notes", "limit": 10}'
```

## Provider setup

### Notion

```bash
curl -X POST http://localhost:8000/api/v1/sync/notion
```

Or set `SPOON_NOTION_API_KEY` for API-key fallback.

### Linear

Set `SPOON_LINEAR_API_KEY`, then sync issues and projects:

```bash
curl -X POST http://localhost:8000/api/v1/sync/linear
```

### Google Drive + Gmail

OAuth at `http://localhost:8000/api/v1/auth/gdrive` (includes PKCE; grants Drive + Gmail).

```bash
curl -X POST http://localhost:8000/api/v1/sync/gdrive
curl -X POST http://localhost:8000/api/v1/sync/gmail
```

Service account fallback: `SPOON_GDRIVE_SERVICE_ACCOUNT_PATH=/path/to/sa.json`

### Outlook

Azure app with **Mail.Read**, redirect URI `http://localhost:8000/api/v1/auth/outlook/callback`.

```bash
curl -X POST http://localhost:8000/api/v1/sync/outlook
```

### Slack

OAuth at `http://localhost:8000/api/v1/auth/slack`, or set `SPOON_SLACK_BOT_TOKEN`.

```bash
curl -X POST http://localhost:8000/api/v1/sync/slack
```

## Tests

```bash
make test
make security
```

## Docker

```bash
docker build -t spoon .
docker run -p 8000:8000 --env-file .env spoon
```

Container runs as non-root user with healthcheck on `/api/v1/health`.
