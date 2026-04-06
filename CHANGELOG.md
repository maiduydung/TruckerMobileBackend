# Changelog

All notable changes to the NhuTin Trucker API.

## [0.7.0] - 2026-04-06

### Added
- **Shipment contract CRUD** (`functions/contracts.py`) — `POST/GET/PUT/DELETE /api/contracts` for creating and managing shipment contracts with target tonnage, price/kg, and date range.
- **Auto-matching trip-to-contract** — `GET /api/contracts` computes `deliveredWeightKg` via a PostgreSQL lateral join that matches trips where any stop (pickup OR delivery) location matches the contract subject, within the contract date range. Only delivery weights are summed.
- **Computed fields** — each contract response includes `completionPct`, `remainingKg`, `contractValueVnd`, `daysLeft`, and `alerting` (true when ≥90% complete).
- **Contract alert endpoint** — `GET /api/alerts/check-contracts` finds active contracts at or above the alert threshold (default 90%) and sends an HTML email via Gmail SMTP. Purple-themed email template matching the existing balance alert style.
- **`contracts` table** — added to `init_db()` in `services/database.py` with columns: `id`, `name`, `subject`, `target_weight_kg`, `price_per_kg`, `start_date`, `end_date`, `status`, `notes`, `created_at`, `updated_at`.

### Configuration
- `CONTRACT_ALERT_THRESHOLD` — completion percentage at which to fire contract alerts (default: `90`)

### Database
- New `contracts` table auto-created on cold start alongside `trips`

## [0.6.0] - 2026-04-06

### Added
- **Low-balance alert endpoint** — `GET /api/alerts/check-balances` checks each driver's latest closing balance against a configurable threshold (default 500,000 VND). Returns list of drivers below threshold and sends email alert.
- **Gmail email service** (`services/email.py`) — sends HTML alert emails via Gmail SMTP using app passwords. Supports multiple recipients via `ALERT_RECIPIENTS` config.
- **Azure Logic App** (`nhutin-balance-alert`) — triggers the balance check 5 times daily at 06:00, 09:00, 12:00, 15:00, 18:00 Vietnam time.
- **Creation script** (`scripts/create_logic_app.sh`) — deploys the Logic App to Azure.

### Configuration
- `LOW_BALANCE_THRESHOLD` — balance threshold in VND (default: 500,000)
- `GMAIL_ADDRESS` — sender Gmail address
- `GMAIL_APP_PASSWORD` — Google app password for SMTP auth
- `ALERT_RECIPIENTS` — comma-separated recipient emails

## [0.5.2] - 2026-04-02

### Fixed
- **Dashboard summary `totalCost`** — added `SUM(total_cost)` to the summary endpoint so "Tổng chi phí" reflects the actual total cost (fuel + loading + additional costs) instead of only fuel + loading.

## [0.5.1] - 2026-04-01

### Changed
- **Updated DB schema docs** — added `opening_balance`, `total_cost`, `closing_balance` columns and `stops` JSONB to the README ER diagram. Documented the client-side balance formula: `closing_balance = opening_balance + advance_payment - (total_cost - fuel_nam_phat_vnd)`.

## [0.5.0] - 2026-04-01

### Added
- **Multi-stop trips** — trips now support multiple pickup and delivery locations via a unified `stops` JSONB array. Each stop has seq, type (pickup/delivery), location, date, weight, and GPS.
- **Backward compatibility shim** — old mobile app versions sending scalar `pickupLocation`/`deliveryLocation` are auto-converted to the stops format.
- **Dashboard computed fields** — `pickup_locations`, `delivery_locations`, `total_pickup_kg`, `total_delivery_kg` derived from stops for the dashboard.

### Changed
- Trip CRUD (POST/PUT) now reads/writes `stops` column instead of the 8 scalar pickup/delivery columns.
- Dashboard summary computes weight totals from stops JSONB in Python.
- Existing trips are backfilled into the stops format on schema init.

## [0.4.1] - 2026-03-29

### Added
- **Test suite** (`tests/`) — pytest tests for `ResponseHelper` CORS logic, JSON responses, preflight handling, and origin allowlist validation (12 tests).

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
