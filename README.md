# NhuTin Trucker API

Azure Function App backend for the trucker mobile app. Uses PostgreSQL.

## Endpoints

| Method | Route | Description |
|--------|-------|-------------|
| POST | `/api/trips` | Submit a trip (`isDraft: true/false`) |
| GET | `/api/trips` | List trips (`?driver=X&includeDrafts=true`) |
| GET | `/api/health` | Health check |

## Setup

1. Set PostgreSQL credentials in `local.settings.json`
2. Run locally:

```bash
pip install -r requirements.txt
func start
```

Table is auto-created on first run.

## Architecture

```
Mobile App → POST /api/trips → PostgreSQL (nhutin.trips)
Dashboard  → reads PostgreSQL directly (or GET /api/trips)
```
