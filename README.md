# NhuTin Trucker API

Azure Function App backend for the trucker mobile app.

## Endpoints

| Method | Route | Description |
|--------|-------|-------------|
| POST | `/api/trips` | Submit a trip (draft or completed) |
| GET | `/api/trips` | List trips (`?driver=X&includeDrafts=true`) |
| GET | `/api/health` | Health check |

## Setup

1. Set Cosmos DB credentials in `local.settings.json`
2. Run locally:

```bash
pip install -r requirements.txt
func start
```

## Architecture

```
Mobile App → POST /api/trips → Cosmos DB (NhuTinTrucker/Trips)
Dashboard  → GET  /api/trips → Cosmos DB (read)
```
