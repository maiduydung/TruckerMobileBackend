# Changelog

All notable changes to the NhuTin Trucker API.

## [0.4.0] - 2026-03-27

### Added
- **Dashboard query endpoints** — `GET /api/dashboard/summary`, `GET /api/dashboard/trips`, `GET /api/dashboard/drivers` for the upcoming owner dashboard.
- **`Database` class** (`services/database.py`) with query helpers, replacing raw `get_conn()` calls.
- **`ResponseHelper` class** (`services/response.py`) with built-in CORS header handling.

### Changed
- **Refactored monolithic `function_app.py`** into `functions/` and `services/` modules — OOP style with docstrings, each file under 300 lines.
- Trip CRUD endpoints moved to `functions/trips.py`.
- Health check and CORS preflight moved to `functions/health.py`.

## [0.3.0] - 2026-03-26

### Added
- **PUT `/api/trips/{trip_id}`** — in-place trip updates with 2-day edit window. Drivers can now correct mistakes (wrong fuel price, missing additional costs) without creating duplicate rows.
- **DELETE `/api/trips/{trip_id}`** — trip deletion for removing junk drafts or wrong-driver submissions.
- **`sinceDays` query parameter** on GET `/api/trips` — enables the mobile app to fetch only recent trips (e.g., last 2 days) instead of the full history.
- CORS support for PUT and DELETE methods.

### Changed
- Trip lifecycle now follows: `draft → submitted → editable (2 days) → locked`. Previously, every save created a new row; now edits update in place.

## [0.2.0] - 2026-03-22

### Changed
- **Migrated from Cosmos DB to PostgreSQL** — Azure Database for PostgreSQL Flexible Server (Burstable tier). Cosmos RU pricing was overkill for simple CRUD on < 100 trips/month. PostgreSQL is ~$13/month vs. unpredictable Cosmos costs.

## [0.1.0] - 2026-03-20

### Added
- Initial API with POST `/api/trips` and GET `/api/trips`.
- PostgreSQL schema auto-creation on cold start.
- Health check endpoint.
- CORS preflight handler.
- GitHub Actions CI/CD pipeline deploying to Azure Function App.
