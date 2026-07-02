# Spoon

Connect Knowledge Bases to Supermemory and search your documents.

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
