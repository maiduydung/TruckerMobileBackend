"""Trip CRUD endpoints — POST, PUT, DELETE, GET."""
import datetime
import json
import logging
import time
import traceback
import uuid

import azure.functions as func

from services.database import Database
from services.response import ResponseHelper

logger = logging.getLogger(__name__)

EDIT_WINDOW_DAYS = 30


class TripFunctions:
    """Registers all trip-related HTTP endpoints."""

    @staticmethod
    def register(app: func.FunctionApp):
        """Bind trip routes to the function app."""

        @app.function_name(name="submit_trip")
        @app.route(route="trips", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
        def submit_trip(req: func.HttpRequest) -> func.HttpResponse:
            """Create a new trip record."""
            return TripFunctions._submit(req)

        @app.function_name(name="update_trip")
        @app.route(route="trips/{trip_id}", methods=["PUT"], auth_level=func.AuthLevel.ANONYMOUS)
        def update_trip(req: func.HttpRequest) -> func.HttpResponse:
            """Update an existing trip within the edit window."""
            return TripFunctions._update(req)

        @app.function_name(name="delete_trip")
        @app.route(route="trips/{trip_id}", methods=["DELETE"], auth_level=func.AuthLevel.ANONYMOUS)
        def delete_trip(req: func.HttpRequest) -> func.HttpResponse:
            """Delete a trip record."""
            return TripFunctions._delete(req)

        @app.function_name(name="get_trips")
        @app.route(route="trips", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
        def get_trips(req: func.HttpRequest) -> func.HttpResponse:
            """List trips with optional filters."""
            return TripFunctions._list(req)

    @staticmethod
    def _build_stops(body: dict) -> list:
        """Build stops array, with backward compat for old single-stop payloads."""
        if "stops" in body and body["stops"]:
            return body["stops"]

        # Backward compat: old mobile app sends scalar pickup/delivery fields
        stops = []
        if body.get("pickupLocation") or body.get("pickupDate"):
            stops.append({
                "seq": 1, "type": "pickup",
                "location": body.get("pickupLocation", ""),
                "date": body.get("pickupDate"),
                "weightKg": body.get("pickupWeightKg", 0),
                "gps": body.get("pickupGps"),
            })
        if body.get("deliveryLocation") or body.get("deliveryDate"):
            stops.append({
                "seq": 2, "type": "delivery",
                "location": body.get("deliveryLocation", ""),
                "date": body.get("deliveryDate"),
                "weightKg": body.get("deliveryWeightKg", 0),
                "gps": body.get("deliveryGps"),
            })
        return stops

    @staticmethod
    def _extract_trip_params(body: dict) -> tuple:
        """Extract trip fields from request body into a parameter tuple."""
        stops = TripFunctions._build_stops(body)
        return (
            body.get("driverName", ""),
            body.get("advancePayment", 0),
            json.dumps(stops),
            body.get("fuelNamPhatVnd", 0),
            body.get("fuelHnLiters", 0),
            body.get("loadingFeeVnd", 0),
            json.dumps(body.get("additionalCosts", [])),
            body.get("openingBalance", 0),
            body.get("totalCost", 0),
            body.get("closingBalance", 0),
            body.get("notes", ""),
            body.get("isDraft", False),
            body.get("submittedAt"),
        )

    @staticmethod
    def _submit(req: func.HttpRequest) -> func.HttpResponse:
        """Handle POST /api/trips."""
        t0 = time.time()
        logger.info("📥 POST /api/trips — new trip incoming")
        try:
            body = req.get_json()
            if not body:
                logger.warning("📥 POST /api/trips — ❌ empty body")
                return ResponseHelper.json({"error": "Request body required"}, 400)

            driver = body.get("driverName", "?")
            is_draft = body.get("isDraft", False)
            stops = TripFunctions._build_stops(body)
            logger.info(f"📥 POST /api/trips — driver={driver} draft={is_draft} stops={len(stops)} "
                        f"advance={body.get('advancePayment', 0)} opening={body.get('openingBalance', 0)} "
                        f"totalCost={body.get('totalCost', 0)} closing={body.get('closingBalance', 0)}")

            trip_id = str(uuid.uuid4())
            params = TripFunctions._extract_trip_params(body)

            Database.execute("""
                INSERT INTO trips (
                    id, driver_name, advance_payment, stops,
                    fuel_nam_phat_vnd, fuel_hn_liters, loading_fee_vnd, additional_costs,
                    opening_balance, total_cost, closing_balance,
                    notes, is_draft, submitted_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, [trip_id, *params])

            ms = int((time.time() - t0) * 1000)
            logger.info(f"📥 POST /api/trips — ✅ saved {trip_id} | driver={driver} draft={is_draft} | {ms}ms")
            return ResponseHelper.json({"status": "ok", "tripId": trip_id, "isDraft": is_draft}, 201)

        except json.JSONDecodeError as e:
            logger.error(f"📥 POST /api/trips — ❌ bad JSON: {e}")
            return ResponseHelper.json({"error": "Invalid JSON"}, 400)
        except Exception:
            logger.error(f"📥 POST /api/trips — 💥 CRASH\n{traceback.format_exc()}")
            return ResponseHelper.json({"error": "Internal server error"}, 500)

    @staticmethod
    def _update(req: func.HttpRequest) -> func.HttpResponse:
        """Handle PUT /api/trips/{trip_id}."""
        t0 = time.time()
        trip_id = req.route_params.get("trip_id")
        logger.info(f"✏️ PUT /api/trips/{trip_id} — update incoming")
        try:
            body = req.get_json()
            if not body:
                logger.warning(f"✏️ PUT /api/trips/{trip_id} — ❌ empty body")
                return ResponseHelper.json({"error": "Request body required"}, 400)

            driver = body.get("driverName", "?")
            logger.info(f"✏️ PUT /api/trips/{trip_id} — driver={driver} draft={body.get('isDraft')} "
                        f"advance={body.get('advancePayment', 0)} closing={body.get('closingBalance', 0)}")

            trip = Database.fetch_one("SELECT id, submitted_at FROM trips WHERE id = %s", [trip_id])
            if not trip:
                logger.warning(f"✏️ PUT /api/trips/{trip_id} — ❌ not found")
                return ResponseHelper.json({"error": "Trip not found"}, 404)

            cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=EDIT_WINDOW_DAYS)
            if trip["submitted_at"] and trip["submitted_at"] < cutoff:
                age_days = (datetime.datetime.now(datetime.timezone.utc) - trip["submitted_at"]).days
                logger.warning(f"✏️ PUT /api/trips/{trip_id} — 🚫 too old ({age_days}d > {EDIT_WINDOW_DAYS}d window)")
                return ResponseHelper.json({"error": f"Trip is older than {EDIT_WINDOW_DAYS} days and cannot be edited"}, 403)

            params = TripFunctions._extract_trip_params(body)
            Database.execute("""
                UPDATE trips SET
                    driver_name = %s, advance_payment = %s, stops = %s,
                    fuel_nam_phat_vnd = %s, fuel_hn_liters = %s, loading_fee_vnd = %s, additional_costs = %s,
                    opening_balance = %s, total_cost = %s, closing_balance = %s,
                    notes = %s, is_draft = %s, submitted_at = %s
                WHERE id = %s
            """, [*params, trip_id])

            ms = int((time.time() - t0) * 1000)
            logger.info(f"✏️ PUT /api/trips/{trip_id} — ✅ updated | driver={driver} | {ms}ms")
            return ResponseHelper.json({"status": "ok", "tripId": trip_id})

        except json.JSONDecodeError as e:
            logger.error(f"✏️ PUT /api/trips/{trip_id} — ❌ bad JSON: {e}")
            return ResponseHelper.json({"error": "Invalid JSON"}, 400)
        except Exception:
            logger.error(f"✏️ PUT /api/trips/{trip_id} — 💥 CRASH\n{traceback.format_exc()}")
            return ResponseHelper.json({"error": "Internal server error"}, 500)

    @staticmethod
    def _delete(req: func.HttpRequest) -> func.HttpResponse:
        """Handle DELETE /api/trips/{trip_id}."""
        t0 = time.time()
        trip_id = req.route_params.get("trip_id")
        logger.info(f"🗑️ DELETE /api/trips/{trip_id} — delete incoming")
        try:
            trip = Database.fetch_one("SELECT id, driver_name FROM trips WHERE id = %s", [trip_id])
            if not trip:
                logger.warning(f"🗑️ DELETE /api/trips/{trip_id} — ❌ not found")
                return ResponseHelper.json({"error": "Trip not found"}, 404)

            Database.execute("DELETE FROM trips WHERE id = %s", [trip_id])
            ms = int((time.time() - t0) * 1000)
            logger.info(f"🗑️ DELETE /api/trips/{trip_id} — ✅ deleted | driver={trip['driver_name']} | {ms}ms")
            return ResponseHelper.json({"status": "ok", "tripId": trip_id})

        except Exception:
            logger.error(f"🗑️ DELETE /api/trips/{trip_id} — 💥 CRASH\n{traceback.format_exc()}")
            return ResponseHelper.json({"error": "Internal server error"}, 500)

    @staticmethod
    def _list(req: func.HttpRequest) -> func.HttpResponse:
        """Handle GET /api/trips with optional filters."""
        t0 = time.time()
        driver = req.params.get("driver", "*")
        since_days = req.params.get("sinceDays", "all")
        include_drafts = req.params.get("includeDrafts", "false").lower() == "true"
        logger.info(f"📋 GET /api/trips — driver={driver} sinceDays={since_days} drafts={include_drafts}")
        try:
            conditions, params = [], []

            if not include_drafts:
                conditions.append("is_draft = FALSE")

            if driver != "*":
                conditions.append("driver_name = %s")
                params.append(driver)

            if since_days != "all":
                try:
                    days = int(since_days)
                    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
                    conditions.append("submitted_at >= %s")
                    params.append(cutoff)
                except ValueError:
                    logger.warning(f"📋 GET /api/trips — ⚠️ invalid sinceDays={since_days}, ignoring")

            where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
            query = f"SELECT * FROM trips{where} ORDER BY submitted_at DESC"
            rows = Database.query(query, params)

            ms = int((time.time() - t0) * 1000)
            logger.info(f"📋 GET /api/trips — ✅ {len(rows)} trips returned | {ms}ms")
            return ResponseHelper.json({"trips": rows, "count": len(rows)})

        except Exception:
            logger.error(f"📋 GET /api/trips — 💥 CRASH\n{traceback.format_exc()}")
            return ResponseHelper.json({"error": "Internal server error"}, 500)


def main():
    """Test trip functions module loads correctly."""
    print("TripFunctions module loaded OK")
    print(f"Edit window: {EDIT_WINDOW_DAYS} days")


if __name__ == "__main__":
    main()
