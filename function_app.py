import logging
import azure.functions as func
import json
import datetime
import traceback
import uuid
import psycopg2
from psycopg2.extras import RealDictCursor

from config import PG_HOST, PG_PORT, PG_DATABASE, PG_USER, PG_PASSWORD, PG_SSLMODE

app = func.FunctionApp()
logger = logging.getLogger(__name__)

# ── PostgreSQL ───────────────────────────────────────────────────────────

def get_conn():
    return psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        dbname=PG_DATABASE,
        user=PG_USER,
        password=PG_PASSWORD,
        sslmode=PG_SSLMODE,
    )


def init_db():
    """Create trips table if it doesn't exist."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS trips (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    driver_name TEXT NOT NULL,
                    advance_payment INTEGER DEFAULT 0,

                    pickup_date TIMESTAMPTZ,
                    pickup_location TEXT,
                    pickup_weight_kg INTEGER DEFAULT 0,
                    pickup_gps JSONB,

                    delivery_date TIMESTAMPTZ,
                    delivery_location TEXT,
                    delivery_weight_kg INTEGER DEFAULT 0,
                    delivery_gps JSONB,

                    fuel_nam_phat_vnd INTEGER DEFAULT 0,
                    fuel_hn_liters INTEGER DEFAULT 0,
                    loading_fee_vnd INTEGER DEFAULT 0,
                    additional_costs JSONB DEFAULT '[]',

                    notes TEXT DEFAULT '',
                    is_draft BOOLEAN DEFAULT FALSE,
                    submitted_at TIMESTAMPTZ,
                    received_at TIMESTAMPTZ DEFAULT NOW()
                );
            """)
        conn.commit()


# Init on cold start
try:
    init_db()
    logger.info("DB initialized")
except Exception:
    logger.warning(f"DB init skipped (will retry on first request): {traceback.format_exc()}")


# ── POST /api/trips ──────────────────────────────────────────────────────

@app.function_name(name="submit_trip")
@app.route(route="trips", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def submit_trip(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json()
        if not body:
            return _json_response({"error": "Request body required"}, 400)

        trip_id = str(uuid.uuid4())

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO trips (
                        id, driver_name, advance_payment,
                        pickup_date, pickup_location, pickup_weight_kg, pickup_gps,
                        delivery_date, delivery_location, delivery_weight_kg, delivery_gps,
                        fuel_nam_phat_vnd, fuel_hn_liters, loading_fee_vnd, additional_costs,
                        notes, is_draft, submitted_at
                    ) VALUES (
                        %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s
                    )
                """, (
                    trip_id,
                    body.get("driverName", ""),
                    body.get("advancePayment", 0),
                    body.get("pickupDate"),
                    body.get("pickupLocation", ""),
                    body.get("pickupWeightKg", 0),
                    json.dumps(body.get("pickupGps")),
                    body.get("deliveryDate"),
                    body.get("deliveryLocation", ""),
                    body.get("deliveryWeightKg", 0),
                    json.dumps(body.get("deliveryGps")),
                    body.get("fuelNamPhatVnd", 0),
                    body.get("fuelHnLiters", 0),
                    body.get("loadingFeeVnd", 0),
                    json.dumps(body.get("additionalCosts", [])),
                    body.get("notes", ""),
                    body.get("isDraft", False),
                    body.get("submittedAt"),
                ))
            conn.commit()

        logger.info(f"Trip saved: {trip_id} | driver={body.get('driverName')} | isDraft={body.get('isDraft')}")

        return _json_response({
            "status": "ok",
            "tripId": trip_id,
            "isDraft": body.get("isDraft", False),
        }, 201)

    except json.JSONDecodeError:
        return _json_response({"error": "Invalid JSON"}, 400)
    except Exception:
        logger.error(f"Error saving trip: {traceback.format_exc()}")
        return _json_response({"error": "Internal server error"}, 500)


# ── GET /api/trips ───────────────────────────────────────────────────────

@app.function_name(name="get_trips")
@app.route(route="trips", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def get_trips(req: func.HttpRequest) -> func.HttpResponse:
    try:
        driver = req.params.get("driver")
        include_drafts = req.params.get("includeDrafts", "false").lower() == "true"

        conditions = []
        params = []

        if not include_drafts:
            conditions.append("is_draft = FALSE")

        if driver:
            conditions.append("driver_name = %s")
            params.append(driver)

        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"SELECT * FROM trips{where} ORDER BY submitted_at DESC"

        with get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)
                rows = cur.fetchall()

        return _json_response({"trips": rows, "count": len(rows)})

    except Exception:
        logger.error(f"Error fetching trips: {traceback.format_exc()}")
        return _json_response({"error": "Internal server error"}, 500)


# ── GET /api/health ──────────────────────────────────────────────────────

@app.function_name(name="health")
@app.route(route="health", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def health(req: func.HttpRequest) -> func.HttpResponse:
    return _json_response({
        "status": "ok",
        "service": "NhuTin Trucker API",
        "time": datetime.datetime.utcnow().isoformat() + "Z",
    })


# ── CORS preflight ───────────────────────────────────────────────────────

@app.function_name(name="cors_preflight")
@app.route(route="{*path}", methods=["OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def cors_preflight(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse(status_code=204, headers=_cors_headers())


# ── Helpers ──────────────────────────────────────────────────────────────

ALLOWED_ORIGINS = {
    "http://localhost:8081",
    "http://localhost:19006",
    "http://localhost:3000",
}


def _cors_headers(origin: str = "*") -> dict:
    return {
        "Access-Control-Allow-Origin": origin if origin in ALLOWED_ORIGINS else "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }


def _json_response(body: dict, status_code: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(body, default=str),
        status_code=status_code,
        headers={
            "Content-Type": "application/json",
            **_cors_headers(),
        },
    )
