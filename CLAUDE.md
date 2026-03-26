# CLAUDE.md — LLM Context for NhuTin Trucker API

## What is this project?

A serverless REST API for a Vietnamese trucking SME (Nhu Tin). It records trip data submitted by truck drivers via a mobile app and will serve an owner dashboard for cost tracking and reporting.

## Tech stack

- **Runtime:** Python 3.11 on Azure Functions (Flex Consumption)
- **Database:** PostgreSQL on Azure Flexible Server
- **Driver:** psycopg2-binary (no ORM)
- **Deployment:** GitHub Actions → `func azure functionapp publish`

## Key files

| File | Purpose |
|------|---------|
| `function_app.py` | All API endpoints — POST, PUT, DELETE, GET for trips, plus health and CORS |
| `config.py` | Reads PG_* env vars for database connection |
| `requirements.txt` | 3 deps: azure-functions, psycopg2-binary, python-dotenv |

## Domain context

- A **trip** = one pickup-to-delivery journey (e.g., TPG → TBS). Not a full day — a driver may do 3+ trips per day.
- **Drivers** self-report trips via the mobile app. There is no assignment system.
- **Additional costs** (`additional_costs` JSONB) are variable — fines, tolls, medical, etc. Each has a name, amount in VND, and a note.
- **Edit window:** Trips are editable for 2 days after submission. After that, the PUT endpoint returns 403.
- **No auth:** Deliberate — 3 trusted drivers, SME context. Friction kills adoption.
- **Currency:** All monetary values are integers in VND (Vietnamese Dong). No decimals.

## API patterns

- All endpoints return JSON with `_json_response()` helper (handles serialization + CORS headers).
- Error responses: `{"error": "message"}` with appropriate HTTP status.
- camelCase in JSON payloads (mobile app convention), snake_case in database columns.
- GPS fields exist in schema but are not yet captured by the mobile app (prepared for future).

## Database

- Single `trips` table, auto-created on cold start by `init_db()`.
- No migrations framework — schema changes are manual (acceptable at this scale).
- Connection per request via `get_conn()` — no pooling (serverless context, short-lived).

## Companion repos

- **TruckerMobile** — React Native / Expo mobile app (the client for this API)
- **Dashboard** — planned, not yet built. Will use Gradio or Svelte static site.
