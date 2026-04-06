"""Contract CRUD endpoints — create, list, update, delete shipment contracts."""
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


class ContractFunctions:
    """Registers contract-related HTTP endpoints."""

    @staticmethod
    def register(app: func.FunctionApp):
        """Bind contract routes to the function app."""

        @app.function_name(name="create_contract")
        @app.route(route="contracts", methods=["POST"],
                   auth_level=func.AuthLevel.ANONYMOUS)
        def create_contract(req: func.HttpRequest) -> func.HttpResponse:
            """Create a new shipment contract."""
            return ContractFunctions._create(req)

        @app.function_name(name="list_contracts")
        @app.route(route="contracts", methods=["GET"],
                   auth_level=func.AuthLevel.ANONYMOUS)
        def list_contracts(req: func.HttpRequest) -> func.HttpResponse:
            """List contracts with auto-computed delivery progress."""
            return ContractFunctions._list(req)

        @app.function_name(name="update_contract")
        @app.route(route="contracts/{contract_id}", methods=["PUT"],
                   auth_level=func.AuthLevel.ANONYMOUS)
        def update_contract(req: func.HttpRequest) -> func.HttpResponse:
            """Update an existing contract."""
            return ContractFunctions._update(req)

        @app.function_name(name="delete_contract")
        @app.route(route="contracts/{contract_id}", methods=["DELETE"],
                   auth_level=func.AuthLevel.ANONYMOUS)
        def delete_contract(req: func.HttpRequest) -> func.HttpResponse:
            """Delete a contract."""
            return ContractFunctions._delete(req)

    @staticmethod
    def _create(req: func.HttpRequest) -> func.HttpResponse:
        """Handle POST /api/contracts."""
        t0 = time.time()
        logger.info("📄 POST /api/contracts — new contract incoming")
        try:
            body = req.get_json()
            if not body:
                logger.warning("📄 POST /api/contracts — ❌ empty body")
                return ResponseHelper.json({"error": "Request body required"}, 400)

            name = body.get("name", "").strip()
            subject = body.get("subject", "").strip()
            target_weight_kg = body.get("targetWeightKg", 0)
            price_per_kg = body.get("pricePerKg", 0)
            start_date = body.get("startDate")
            end_date = body.get("endDate")
            notes = body.get("notes", "")

            if not name or not subject or not target_weight_kg or not start_date or not end_date:
                logger.warning("📄 POST /api/contracts — ❌ missing required fields")
                return ResponseHelper.json(
                    {"error": "name, subject, targetWeightKg, startDate, endDate are required"}, 400
                )

            contract_id = str(uuid.uuid4())
            Database.execute("""
                INSERT INTO contracts (id, name, subject, target_weight_kg, price_per_kg,
                                       start_date, end_date, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, [contract_id, name, subject, target_weight_kg, price_per_kg,
                  start_date, end_date, notes])

            ms = int((time.time() - t0) * 1000)
            logger.info(f"📄 POST /api/contracts — ✅ saved {contract_id} | "
                        f"name={name} subject={subject} target={target_weight_kg}kg | {ms}ms")
            return ResponseHelper.json({"status": "ok", "contractId": contract_id}, 201)

        except json.JSONDecodeError as e:
            logger.error(f"📄 POST /api/contracts — ❌ bad JSON: {e}")
            return ResponseHelper.json({"error": "Invalid JSON"}, 400)
        except Exception:
            logger.error(f"📄 POST /api/contracts — 💥 CRASH\n{traceback.format_exc()}")
            return ResponseHelper.json({"error": "Internal server error"}, 500)

    @staticmethod
    def _list(req: func.HttpRequest) -> func.HttpResponse:
        """Handle GET /api/contracts — list with auto-computed delivery progress."""
        t0 = time.time()
        status_filter = req.params.get("status", "")
        logger.info(f"📄 GET /api/contracts — status={status_filter or '*'}")
        try:
            conditions, params = [], []
            if status_filter:
                conditions.append("c.status = %s")
                params.append(status_filter)

            where = f" WHERE {' AND '.join(conditions)}" if conditions else ""

            rows = Database.query(f"""
                SELECT c.*,
                       COALESCE(matched.delivered_kg, 0) AS delivered_weight_kg
                FROM contracts c
                LEFT JOIN LATERAL (
                    SELECT SUM(del_weight) AS delivered_kg
                    FROM (
                        SELECT DISTINCT t.id,
                            (SELECT COALESCE(SUM((ds->>'weightKg')::int), 0)
                             FROM jsonb_array_elements(t.stops) ds
                             WHERE (ds->>'type') = 'delivery'
                            ) AS del_weight
                        FROM trips t, jsonb_array_elements(t.stops) AS stop
                        WHERE LOWER(TRIM(stop->>'location')) = LOWER(TRIM(c.subject))
                          AND t.submitted_at >= c.start_date
                          AND t.submitted_at <= c.end_date + interval '1 day'
                          AND t.is_draft = FALSE
                    ) matched_trips
                ) matched ON true
                {where}
                ORDER BY c.end_date ASC
            """, params)

            now = datetime.date.today()
            contracts = []
            for row in rows:
                target = row["target_weight_kg"]
                delivered = row["delivered_weight_kg"] or 0
                remaining = max(target - delivered, 0)
                pct = round((delivered / target) * 100, 1) if target > 0 else 0
                end = row["end_date"]
                days_left = (end - now).days if isinstance(end, datetime.date) else 0
                value = target * row["price_per_kg"] * 1000
                alerting = pct >= 90 and row["status"] == "active"

                contracts.append({
                    "id": row["id"],
                    "name": row["name"],
                    "subject": row["subject"],
                    "targetWeightKg": target,
                    "deliveredWeightKg": delivered,
                    "pricePerKg": row["price_per_kg"],
                    "startDate": row["start_date"],
                    "endDate": row["end_date"],
                    "status": row["status"],
                    "completionPct": pct,
                    "remainingKg": remaining,
                    "contractValueVnd": value,
                    "daysLeft": days_left,
                    "alerting": alerting,
                    "notes": row["notes"],
                    "createdAt": row["created_at"],
                    "updatedAt": row["updated_at"],
                })

            ms = int((time.time() - t0) * 1000)
            logger.info(f"📄 GET /api/contracts — ✅ {len(contracts)} contracts returned | {ms}ms")
            return ResponseHelper.json({"contracts": contracts, "count": len(contracts)})

        except Exception:
            logger.error(f"📄 GET /api/contracts — 💥 CRASH\n{traceback.format_exc()}")
            return ResponseHelper.json({"error": "Internal server error"}, 500)

    @staticmethod
    def _update(req: func.HttpRequest) -> func.HttpResponse:
        """Handle PUT /api/contracts/{contract_id}."""
        t0 = time.time()
        contract_id = req.route_params.get("contract_id")
        logger.info(f"📄 PUT /api/contracts/{contract_id} — update incoming")
        try:
            body = req.get_json()
            if not body:
                logger.warning(f"📄 PUT /api/contracts/{contract_id} — ❌ empty body")
                return ResponseHelper.json({"error": "Request body required"}, 400)

            existing = Database.fetch_one(
                "SELECT id FROM contracts WHERE id = %s", [contract_id]
            )
            if not existing:
                logger.warning(f"📄 PUT /api/contracts/{contract_id} — ❌ not found")
                return ResponseHelper.json({"error": "Contract not found"}, 404)

            Database.execute("""
                UPDATE contracts SET
                    name = %s, subject = %s, target_weight_kg = %s, price_per_kg = %s,
                    start_date = %s, end_date = %s, status = %s, notes = %s,
                    updated_at = NOW()
                WHERE id = %s
            """, [
                body.get("name", "").strip(),
                body.get("subject", "").strip(),
                body.get("targetWeightKg", 0),
                body.get("pricePerKg", 0),
                body.get("startDate"),
                body.get("endDate"),
                body.get("status", "active"),
                body.get("notes", ""),
                contract_id,
            ])

            ms = int((time.time() - t0) * 1000)
            logger.info(f"📄 PUT /api/contracts/{contract_id} — ✅ updated | {ms}ms")
            return ResponseHelper.json({"status": "ok", "contractId": contract_id})

        except json.JSONDecodeError as e:
            logger.error(f"📄 PUT /api/contracts/{contract_id} — ❌ bad JSON: {e}")
            return ResponseHelper.json({"error": "Invalid JSON"}, 400)
        except Exception:
            logger.error(f"📄 PUT /api/contracts/{contract_id} — 💥 CRASH\n{traceback.format_exc()}")
            return ResponseHelper.json({"error": "Internal server error"}, 500)

    @staticmethod
    def _delete(req: func.HttpRequest) -> func.HttpResponse:
        """Handle DELETE /api/contracts/{contract_id}."""
        t0 = time.time()
        contract_id = req.route_params.get("contract_id")
        logger.info(f"📄 DELETE /api/contracts/{contract_id} — delete incoming")
        try:
            existing = Database.fetch_one(
                "SELECT id, name FROM contracts WHERE id = %s", [contract_id]
            )
            if not existing:
                logger.warning(f"📄 DELETE /api/contracts/{contract_id} — ❌ not found")
                return ResponseHelper.json({"error": "Contract not found"}, 404)

            Database.execute("DELETE FROM contracts WHERE id = %s", [contract_id])
            ms = int((time.time() - t0) * 1000)
            logger.info(f"📄 DELETE /api/contracts/{contract_id} — ✅ deleted | "
                        f"name={existing['name']} | {ms}ms")
            return ResponseHelper.json({"status": "ok", "contractId": contract_id})

        except Exception:
            logger.error(f"📄 DELETE /api/contracts/{contract_id} — 💥 CRASH\n{traceback.format_exc()}")
            return ResponseHelper.json({"error": "Internal server error"}, 500)


def main():
    """Test contract functions module loads correctly."""
    print("ContractFunctions module loaded OK")
    rows = Database.query("SELECT COUNT(*) as cnt FROM contracts")
    print(f"Contracts in DB: {rows[0]['cnt']}")


if __name__ == "__main__":
    main()
