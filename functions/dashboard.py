"""Dashboard query endpoints for the owner dashboard SPA."""
import datetime
import json
import logging
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
                pass

        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        return where, params

    @staticmethod
    def _summary(req: func.HttpRequest) -> func.HttpResponse:
        """Handle GET /api/dashboard/summary."""
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
                    COALESCE(SUM(pickup_weight_kg), 0) AS total_pickup_kg,
                    COALESCE(SUM(delivery_weight_kg), 0) AS total_delivery_kg
                FROM trips{where}
            """, params)

            return ResponseHelper.json({
                "totalTrips": row["total_trips"],
                "completedTrips": row["completed_trips"],
                "draftTrips": row["draft_trips"],
                "totalAdvance": row["total_advance"],
                "totalFuel": row["total_fuel"],
                "totalLoading": row["total_loading"],
                "totalPickupKg": row["total_pickup_kg"],
                "totalDeliveryKg": row["total_delivery_kg"],
            })

        except Exception:
            logger.error(f"Error fetching dashboard summary: {traceback.format_exc()}")
            return ResponseHelper.json({"error": "Internal server error"}, 500)

    @staticmethod
    def _trips(req: func.HttpRequest) -> func.HttpResponse:
        """Handle GET /api/dashboard/trips — full trip list with additional cost totals."""
        try:
            where, params = DashboardFunctions._parse_filters(req)

            rows = Database.query(f"""
                SELECT
                    id, driver_name, advance_payment,
                    pickup_date, pickup_location, pickup_weight_kg,
                    delivery_date, delivery_location, delivery_weight_kg,
                    fuel_nam_phat_vnd, fuel_hn_liters, loading_fee_vnd,
                    additional_costs, opening_balance, total_cost, closing_balance,
                    notes, is_draft, submitted_at
                FROM trips{where}
                ORDER BY submitted_at DESC
            """, params)

            trips = []
            for row in rows:
                additional_total = DashboardFunctions._sum_additional(row["additional_costs"])
                total_cost = row["fuel_nam_phat_vnd"] + row["loading_fee_vnd"] + additional_total
                trips.append({
                    **{k: v for k, v in row.items()},
                    "additionalTotal": additional_total,
                    "totalCost": total_cost,
                })

            return ResponseHelper.json({"trips": trips, "count": len(trips)})

        except Exception:
            logger.error(f"Error fetching dashboard trips: {traceback.format_exc()}")
            return ResponseHelper.json({"error": "Internal server error"}, 500)

    @staticmethod
    def _drivers(req: func.HttpRequest) -> func.HttpResponse:
        """Handle GET /api/dashboard/drivers."""
        try:
            rows = Database.query("SELECT DISTINCT driver_name FROM trips ORDER BY driver_name")
            return ResponseHelper.json({"drivers": [r["driver_name"] for r in rows]})

        except Exception:
            logger.error(f"Error fetching drivers: {traceback.format_exc()}")
            return ResponseHelper.json({"error": "Internal server error"}, 500)

    @staticmethod
    def _sum_additional(costs) -> int:
        """Sum amountVnd from additional_costs JSONB."""
        try:
            items = json.loads(costs) if isinstance(costs, str) else costs
            if isinstance(items, list):
                return sum(c.get("amountVnd", 0) for c in items)
        except (json.JSONDecodeError, TypeError):
            pass
        return 0


def main():
    """Test dashboard query functions."""
    summary = Database.fetch_one("SELECT COUNT(*) AS cnt FROM trips")
    print(f"Dashboard module OK — {summary['cnt']} trips available")


if __name__ == "__main__":
    main()
