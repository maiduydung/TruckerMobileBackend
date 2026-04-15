"""Dashboard query endpoints for the owner dashboard SPA."""
import datetime
import json
import logging
import time
import traceback

import azure.functions as func

from services.database import Database
from services.response import ResponseHelper

logger = logging.getLogger(__name__)


class DashboardFunctions:
    """Registers dashboard-specific read endpoints."""

    @staticmethod
    def register(app: func.FunctionApp):
        """Bind dashboard routes to the function app."""

        @app.function_name(name="dashboard_summary")
        @app.route(route="dashboard/summary", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
        def dashboard_summary(req: func.HttpRequest) -> func.HttpResponse:
            """Aggregated metrics for the dashboard cards."""
            return DashboardFunctions._summary(req)

        @app.function_name(name="dashboard_trips")
        @app.route(route="dashboard/trips", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
        def dashboard_trips(req: func.HttpRequest) -> func.HttpResponse:
            """Filtered trip list with computed fields for the dashboard."""
            return DashboardFunctions._trips(req)

        @app.function_name(name="dashboard_locations")
        @app.route(route="dashboard/locations", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
        def dashboard_locations(req: func.HttpRequest) -> func.HttpResponse:
            del req
            return DashboardFunctions._locations()

        @app.function_name(name="dashboard_drivers")
        @app.route(route="dashboard/drivers", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
        def dashboard_drivers(req: func.HttpRequest) -> func.HttpResponse:
            """List of distinct driver names."""
            return DashboardFunctions._drivers(req)

    @staticmethod
    def _parse_filters(req: func.HttpRequest) -> tuple[str, list]:
        """Build WHERE clause from query params."""
        conditions, params = [], []

        driver = req.params.get("driver")
        if driver:
            conditions.append("driver_name = %s")
            params.append(driver)

        status = req.params.get("status")
        if status == "completed":
            conditions.append("is_draft = FALSE")
        elif status == "draft":
            conditions.append("is_draft = TRUE")

        days = req.params.get("days")
        if days and days != "0":
            try:
                cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=int(days))
                conditions.append("submitted_at >= %s")
                params.append(cutoff)
            except ValueError:
                logger.warning(f"📊 dashboard — ⚠️ invalid days={days}, ignoring")

        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        logger.info(f"📊 dashboard filters — driver={driver or '*'} status={status or '*'} days={days or 'all'}")
        return where, params

    @staticmethod
    def _summary(req: func.HttpRequest) -> func.HttpResponse:
        """Handle GET /api/dashboard/summary."""
        t0 = time.time()
        logger.info("📊 GET /api/dashboard/summary — fetching")
        try:
            where, params = DashboardFunctions._parse_filters(req)

            row = Database.fetch_one(f"""
                SELECT
                    COUNT(*) AS total_trips,
                    COUNT(*) FILTER (WHERE is_draft = FALSE) AS completed_trips,
                    COUNT(*) FILTER (WHERE is_draft = TRUE) AS draft_trips,
                    COALESCE(SUM(advance_payment), 0) AS total_advance,
                    COALESCE(SUM(fuel_nam_phat_vnd), 0) AS total_fuel,
                    COALESCE(SUM(loading_fee_vnd), 0) AS total_loading,
                    COALESCE(SUM(total_cost), 0) AS total_cost
                FROM trips{where}
            """, params)

            # Compute weights from stops JSONB
            rows = Database.query(f"SELECT stops FROM trips{where}", params)
            total_pickup_kg = 0
            total_delivery_kg = 0
            for r in rows:
                summary = DashboardFunctions._stops_summary(r["stops"])
                total_pickup_kg += summary["total_pickup_kg"]
                total_delivery_kg += summary["total_delivery_kg"]

            ms = int((time.time() - t0) * 1000)
            logger.info(f"📊 GET /api/dashboard/summary — ✅ {row['total_trips']} trips "
                        f"({row['completed_trips']} done, {row['draft_trips']} draft) | {ms}ms")
            return ResponseHelper.json({
                "totalTrips": row["total_trips"],
                "completedTrips": row["completed_trips"],
                "draftTrips": row["draft_trips"],
                "totalAdvance": row["total_advance"],
                "totalFuel": row["total_fuel"],
                "totalLoading": row["total_loading"],
                "totalCost": row["total_cost"],
                "totalPickupKg": total_pickup_kg,
                "totalDeliveryKg": total_delivery_kg,
            })

        except Exception:
            logger.error(f"📊 GET /api/dashboard/summary — 💥 CRASH\n{traceback.format_exc()}")
            return ResponseHelper.json({"error": "Internal server error"}, 500)

    @staticmethod
    def _trips(req: func.HttpRequest) -> func.HttpResponse:
        """Handle GET /api/dashboard/trips — full trip list with additional cost totals."""
        t0 = time.time()
        logger.info("📊 GET /api/dashboard/trips — fetching")
        try:
            where, params = DashboardFunctions._parse_filters(req)

            rows = Database.query(f"""
                SELECT
                    id, driver_name, advance_payment, stops,
                    fuel_nam_phat_vnd, fuel_hn_liters, loading_fee_vnd,
                    additional_costs, opening_balance, total_cost, closing_balance,
                    notes, is_draft, submitted_at, received_at
                FROM trips{where}
                ORDER BY submitted_at DESC
            """, params)

            trips = []
            for row in rows:
                additional_total = DashboardFunctions._sum_additional(row["additional_costs"])
                total_cost = row["fuel_nam_phat_vnd"] + row["loading_fee_vnd"] + additional_total
                stops_info = DashboardFunctions._stops_summary(row["stops"])
                trips.append({
                    **{k: v for k, v in row.items()},
                    "additionalTotal": additional_total,
                    "totalCost": total_cost,
                    **stops_info,
                })

            ms = int((time.time() - t0) * 1000)
            logger.info(f"📊 GET /api/dashboard/trips — ✅ {len(trips)} trips returned | {ms}ms")
            return ResponseHelper.json({"trips": trips, "count": len(trips)})

        except Exception:
            logger.error(f"📊 GET /api/dashboard/trips — 💥 CRASH\n{traceback.format_exc()}")
            return ResponseHelper.json({"error": "Internal server error"}, 500)

    @staticmethod
    def _locations() -> func.HttpResponse:
        """Handle GET /api/dashboard/locations — all unique pickup/delivery locations."""
        t0 = time.time()
        logger.info("📊 GET /api/dashboard/locations — fetching")
        try:
            rows = Database.query("""
                SELECT DISTINCT
                    stop->>'type'     AS type,
                    stop->>'location' AS location
                FROM trips,
                     jsonb_array_elements(stops::jsonb) AS stop
                WHERE stop->>'type' IN ('pickup', 'delivery')
                  AND COALESCE(stop->>'location', '') <> ''
                ORDER BY type, location
            """)
            pickups = sorted({r["location"] for r in rows if r["type"] == "pickup"})
            deliveries = sorted({r["location"] for r in rows if r["type"] == "delivery"})
            ms = int((time.time() - t0) * 1000)
            logger.info(f"📊 GET /api/dashboard/locations — ✅ {len(pickups)} pickups, {len(deliveries)} deliveries | {ms}ms")
            return ResponseHelper.json({"pickups": pickups, "deliveries": deliveries})

        except Exception:
            logger.error(f"📊 GET /api/dashboard/locations — 💥 CRASH\n{traceback.format_exc()}")
            return ResponseHelper.json({"error": "Internal server error"}, 500)

    @staticmethod
    def _drivers(req: func.HttpRequest) -> func.HttpResponse:
        """Handle GET /api/dashboard/drivers."""
        t0 = time.time()
        logger.info("📊 GET /api/dashboard/drivers — fetching")
        try:
            rows = Database.query("SELECT DISTINCT driver_name FROM trips ORDER BY driver_name")
            drivers = [r["driver_name"] for r in rows]
            ms = int((time.time() - t0) * 1000)
            logger.info(f"📊 GET /api/dashboard/drivers — ✅ {len(drivers)} drivers: {drivers} | {ms}ms")
            return ResponseHelper.json({"drivers": drivers})

        except Exception:
            logger.error(f"📊 GET /api/dashboard/drivers — 💥 CRASH\n{traceback.format_exc()}")
            return ResponseHelper.json({"error": "Internal server error"}, 500)

    @staticmethod
    def _parse_stops(stops) -> list:
        """Parse stops JSONB into a list of dicts."""
        try:
            items = json.loads(stops) if isinstance(stops, str) else stops
            if isinstance(items, list):
                return items
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"📊 _parse_stops — ⚠️ bad stops data: {type(stops)} {str(stops)[:100]}")
        return []

    @staticmethod
    def _stops_summary(stops) -> dict:
        """Compute pickup/delivery locations and weights from stops."""
        parsed = DashboardFunctions._parse_stops(stops)
        pickups = [s for s in parsed if s.get("type") == "pickup"]
        deliveries = [s for s in parsed if s.get("type") == "delivery"]
        return {
            "pickup_locations": ", ".join(s.get("location", "") for s in pickups),
            "delivery_locations": ", ".join(s.get("location", "") for s in deliveries),
            "total_pickup_kg": sum(s.get("weightKg", 0) for s in pickups),
            "total_delivery_kg": sum(s.get("weightKg", 0) for s in deliveries),
        }

    @staticmethod
    def _sum_additional(costs) -> int:
        """Sum amountVnd from additional_costs JSONB."""
        try:
            items = json.loads(costs) if isinstance(costs, str) else costs
            if isinstance(items, list):
                return sum(c.get("amountVnd", 0) for c in items)
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"📊 _sum_additional — ⚠️ bad costs data: {type(costs)} {str(costs)[:100]}")
        return 0


def main():
    """Test dashboard query functions."""
    summary = Database.fetch_one("SELECT COUNT(*) AS cnt FROM trips")
    print(f"Dashboard module OK — {summary['cnt']} trips available")


if __name__ == "__main__":
    main()
