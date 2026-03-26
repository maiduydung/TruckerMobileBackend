"""Trip CRUD endpoints — POST, PUT, DELETE, GET."""
import datetime
import json
import logging
import traceback
import uuid

import azure.functions as func

from services.database import Database
from services.response import ResponseHelper

logger = logging.getLogger(__name__)

EDIT_WINDOW_DAYS = 2


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
    def _extract_trip_params(body: dict) -> tuple:
        """Extract trip fields from request body into a parameter tuple."""
        return (
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
        )

    @staticmethod
    def _submit(req: func.HttpRequest) -> func.HttpResponse:
        """Handle POST /api/trips."""
        try:
            body = req.get_json()
            if not body:
                return ResponseHelper.json({"error": "Request body required"}, 400)

            trip_id = str(uuid.uuid4())
            params = TripFunctions._extract_trip_params(body)

            Database.execute("""
                INSERT INTO trips (
                    id, driver_name, advance_payment,
                    pickup_date, pickup_location, pickup_weight_kg, pickup_gps,
                    delivery_date, delivery_location, delivery_weight_kg, delivery_gps,
                    fuel_nam_phat_vnd, fuel_hn_liters, loading_fee_vnd, additional_costs,
                    notes, is_draft, submitted_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, [trip_id, *params])

            logger.info(f"Trip saved: {trip_id} | driver={body.get('driverName')} | isDraft={body.get('isDraft')}")
            return ResponseHelper.json({"status": "ok", "tripId": trip_id, "isDraft": body.get("isDraft", False)}, 201)

        except json.JSONDecodeError:
            return ResponseHelper.json({"error": "Invalid JSON"}, 400)
        except Exception:
            logger.error(f"Error saving trip: {traceback.format_exc()}")
            return ResponseHelper.json({"error": "Internal server error"}, 500)

    @staticmethod
    def _update(req: func.HttpRequest) -> func.HttpResponse:
        """Handle PUT /api/trips/{trip_id}."""
        try:
            trip_id = req.route_params.get("trip_id")
            body = req.get_json()
            if not body:
                return ResponseHelper.json({"error": "Request body required"}, 400)

            trip = Database.fetch_one("SELECT id, submitted_at FROM trips WHERE id = %s", [trip_id])
            if not trip:
                return ResponseHelper.json({"error": "Trip not found"}, 404)

            cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=EDIT_WINDOW_DAYS)
            if trip["submitted_at"] and trip["submitted_at"] < cutoff:
                return ResponseHelper.json({"error": "Trip is older than 2 days and cannot be edited"}, 403)

            params = TripFunctions._extract_trip_params(body)
            Database.execute("""
                UPDATE trips SET
                    driver_name = %s, advance_payment = %s,
                    pickup_date = %s, pickup_location = %s, pickup_weight_kg = %s, pickup_gps = %s,
                    delivery_date = %s, delivery_location = %s, delivery_weight_kg = %s, delivery_gps = %s,
                    fuel_nam_phat_vnd = %s, fuel_hn_liters = %s, loading_fee_vnd = %s, additional_costs = %s,
                    notes = %s, is_draft = %s, submitted_at = %s
                WHERE id = %s
            """, [*params, trip_id])

            logger.info(f"Trip updated: {trip_id} | driver={body.get('driverName')}")
            return ResponseHelper.json({"status": "ok", "tripId": trip_id})

        except json.JSONDecodeError:
            return ResponseHelper.json({"error": "Invalid JSON"}, 400)
        except Exception:
            logger.error(f"Error updating trip: {traceback.format_exc()}")
            return ResponseHelper.json({"error": "Internal server error"}, 500)

    @staticmethod
    def _delete(req: func.HttpRequest) -> func.HttpResponse:
        """Handle DELETE /api/trips/{trip_id}."""
        try:
            trip_id = req.route_params.get("trip_id")

            trip = Database.fetch_one("SELECT id FROM trips WHERE id = %s", [trip_id])
            if not trip:
                return ResponseHelper.json({"error": "Trip not found"}, 404)

            Database.execute("DELETE FROM trips WHERE id = %s", [trip_id])
            logger.info(f"Trip deleted: {trip_id}")
            return ResponseHelper.json({"status": "ok", "tripId": trip_id})

        except Exception:
            logger.error(f"Error deleting trip: {traceback.format_exc()}")
            return ResponseHelper.json({"error": "Internal server error"}, 500)

    @staticmethod
    def _list(req: func.HttpRequest) -> func.HttpResponse:
        """Handle GET /api/trips with optional filters."""
        try:
            driver = req.params.get("driver")
            include_drafts = req.params.get("includeDrafts", "false").lower() == "true"
            since_days = req.params.get("sinceDays")

            conditions, params = [], []

            if not include_drafts:
                conditions.append("is_draft = FALSE")

            if driver:
                conditions.append("driver_name = %s")
                params.append(driver)

            if since_days:
                try:
                    days = int(since_days)
                    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
                    conditions.append("submitted_at >= %s")
                    params.append(cutoff)
                except ValueError:
                    pass

            where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
            query = f"SELECT * FROM trips{where} ORDER BY submitted_at DESC"
            rows = Database.query(query, params)

            return ResponseHelper.json({"trips": rows, "count": len(rows)})

        except Exception:
            logger.error(f"Error fetching trips: {traceback.format_exc()}")
            return ResponseHelper.json({"error": "Internal server error"}, 500)


def main():
    """Test trip functions module loads correctly."""
    print("TripFunctions module loaded OK")
    print(f"Edit window: {EDIT_WINDOW_DAYS} days")


if __name__ == "__main__":
    main()
