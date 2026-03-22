import logging
import azure.functions as func
import json
import datetime
import traceback
import uuid
from azure.cosmos import CosmosClient, PartitionKey

from config import (
    COSMOS_ENDPOINT,
    COSMOS_KEY,
    COSMOS_DATABASE,
    COSMOS_CONTAINER_TRIPS,
)

app = func.FunctionApp()
logger = logging.getLogger(__name__)

# ── Cosmos DB setup ──────────────────────────────────────────────────────

_container = None


def get_container():
    global _container
    if _container is None:
        client = CosmosClient(COSMOS_ENDPOINT, COSMOS_KEY)
        db = client.create_database_if_not_exists(COSMOS_DATABASE)
        _container = db.create_container_if_not_exists(
            id=COSMOS_CONTAINER_TRIPS,
            partition_key=PartitionKey(path="/driverName"),
        )
    return _container


# ── POST /api/trips ──────────────────────────────────────────────────────

@app.function_name(name="submit_trip")
@app.route(route="trips", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def submit_trip(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json()
        if not body:
            return _json_response({"error": "Request body required"}, 400)

        # Add server-side metadata
        body["id"] = str(uuid.uuid4())
        body["receivedAt"] = datetime.datetime.utcnow().isoformat() + "Z"

        # Write to Cosmos
        container = get_container()
        container.upsert_item(body)

        logger.info(f"Trip saved: {body['id']} | driver={body.get('driverName')} | isDraft={body.get('isDraft')}")

        return _json_response({
            "status": "ok",
            "tripId": body["id"],
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
        container = get_container()

        # Optional filters
        driver = req.params.get("driver")
        include_drafts = req.params.get("includeDrafts", "false").lower() == "true"

        conditions = []
        params = []

        if not include_drafts:
            conditions.append("c.isDraft = false")

        if driver:
            conditions.append("c.driverName = @driver")
            params.append({"name": "@driver", "value": driver})

        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"SELECT * FROM c{where} ORDER BY c.submittedAt DESC"

        items = list(container.query_items(query=query, parameters=params, enable_cross_partition_query=True))

        return _json_response({"trips": items, "count": len(items)})

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


# ── Helpers ──────────────────────────────────────────────────────────────

def _json_response(body: dict, status_code: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(body, default=str),
        status_code=status_code,
        headers={"Content-Type": "application/json"},
    )
