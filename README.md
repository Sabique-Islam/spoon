# Spoon

Connect Knowledge Bases to Supermemory and search your documents.

> for teams, self host supermemory

## Run

```bash
make dev
```

## API

All endpoints are under `/api/v1`.

### Health

```bash
curl http://localhost:8000/api/v1/health
```

### Providers

```bash
curl http://localhost:8000/api/v1/providers
```

### Sync Notion

```bash
curl -X POST http://localhost:8000/api/v1/sync/notion
```

### Sync Linear

Set `SPOON_LINEAR_API_KEY` in `.env`, then:

```bash
curl -X POST http://localhost:8000/api/v1/sync/linear
```

Syncs Linear **issues and projects** from your workspace.

### Sync Google Drive

OAuth (also grants Gmail access):

```
http://localhost:8000/api/v1/auth/gdrive
```

Then:

```bash
curl -X POST http://localhost:8000/api/v1/sync/gdrive
```

Or set `SPOON_GDRIVE_API_KEY` to a service account JSON file path to skip OAuth.

Enable **Google Drive API** and **Gmail API** on your Google Cloud project.

### Sync Gmail

Uses the same Google OAuth token as Drive — no separate auth step.

```bash
curl -X POST http://localhost:8000/api/v1/sync/gmail
```

If Gmail sync fails with a scope error, re-run OAuth at `/api/v1/auth/gdrive` to grant `gmail.readonly`.

### Sync Slack

OAuth:

```
http://localhost:8000/api/v1/auth/slack
```

Then:

```bash
curl -X POST http://localhost:8000/api/v1/sync/slack
```

Or set `SPOON_SLACK_BOT_TOKEN` to skip OAuth. Syncs workspace metadata (team, users, user groups, files, emoji) plus one document per channel/DM with topic, members, pins, bookmarks, messages, and thread replies. Re-run OAuth after scope changes.

### Sync all connected providers

```bash
curl -X POST http://localhost:8000/api/v1/sync/all
```

### Search

```bash
curl -X POST http://localhost:8000/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{"query": "meeting notes", "limit": 10}'
```

## Tests

```bash
make test
```

## Docker

```bash
docker build -t spoon .
docker run -p 8000:8000 --env-file .env spoon
```
