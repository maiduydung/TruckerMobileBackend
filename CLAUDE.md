# CLAUDE.md — LLM Context for NhuTin Trucker API

## What is this project?

A serverless REST API for a Vietnamese trucking SME (Nhu Tin). It records trip data submitted by truck drivers via a mobile app and serves dashboard data for the owner's cost tracking SPA.

## Tech stack

- **Runtime:** Python 3.11 on Azure Functions (Flex Consumption)
- **Database:** PostgreSQL on Azure Flexible Server
- **Driver:** psycopg2-binary (no ORM)
- **Deployment:** GitHub Actions → `func azure functionapp publish`

## Project structure

```
├── function_app.py          # Entry point — registers all route modules
├── config.py                # Reads PG_* env vars / local.settings.json
├── functions/
│   ├── trips.py             # CRUD endpoints: POST, PUT, DELETE, GET /api/trips
│   ├── dashboard.py         # Read endpoints: /api/dashboard/summary, trips, drivers
│   └── health.py            # GET /api/health + CORS preflight
├── services/
│   ├── database.py          # Database class — connection, schema init, query helpers
│   └── response.py          # ResponseHelper — JSON responses + CORS headers
├── docs/
│   └── RULES.md             # AI governance rules
```

## Code conventions (from RULES.md)

- OOP: classes and methods for readability
- Every function has a docstring
- Every file has a `main()` function for standalone testing
- No file longer than 300 lines
- Structured error handling with specific failure modes

## Domain context

- A **trip** = one pickup-to-delivery journey (e.g., TPG → TBS). Not a full day — a driver may do 3+ trips per day.
- **Drivers** self-report trips via the mobile app. There is no assignment system.
- **Additional costs** (`additional_costs` JSONB) have preset categories (Xe xúc, Lò hơi, Cân xe, etc.) plus free-text. Each has a name, amount in VND, and a note.
- **Edit window:** Trips are editable for 2 days after submission. After that, the PUT endpoint returns 403.
- **No auth:** Deliberate — 3 trusted drivers, SME context. Friction kills adoption.
- **Currency:** All monetary values are integers in VND (Vietnamese Dong). No decimals.
- **Balance is client-calculated:** `closing_balance = opening_balance + advance_payment - (total_cost - fuel_nam_phat_vnd)`. The mobile app computes this and sends it; the backend stores it as-is. No server-side recalculation.

## API endpoints

| Method | Route | Purpose |
|--------|-------|---------|
| POST | /api/trips | Create a new trip |
| PUT | /api/trips/{id} | Update trip (2-day window) |
| DELETE | /api/trips/{id} | Delete a trip |
| GET | /api/trips | List trips (filters: driver, sinceDays, includeDrafts) |
| GET | /api/dashboard/summary | Aggregated metrics for dashboard |
| GET | /api/dashboard/trips | Trip list with computed costs |
| GET | /api/dashboard/drivers | Distinct driver names |
| GET | /api/health | Health check |

## API patterns

- All endpoints return JSON via `ResponseHelper.json()` (handles serialization + CORS).
- Error responses: `{"error": "message"}` with appropriate HTTP status.
- camelCase in JSON payloads (mobile app convention), snake_case in database columns.
- GPS fields exist in schema but are not yet captured by the mobile app (prepared for future).

## Database

- Single `trips` table, auto-created on cold start by `Database.init_db()`.
- No migrations framework — schema changes are manual (acceptable at this scale).
- Connection per request via `Database.get_conn()` — no pooling (serverless context).

## Companion repos

- **TruckerMobile** — React Native / Expo mobile app (the client for this API)
- **TruckerDashboard** — Svelte SPA for owner dashboard (reads from /api/dashboard/* endpoints)
