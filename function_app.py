"""NhuTin Trucker API — Azure Functions entry point.

Registers all endpoint modules and initializes the database on cold start.
"""
import azure.functions as func

from services.database import cold_start
from functions.trips import TripFunctions
from functions.dashboard import DashboardFunctions
from functions.health import HealthFunctions

# ── Cold start ────────────────────────────────────────────────────────────
cold_start()

# ── Register all routes ───────────────────────────────────────────────────
app = func.FunctionApp()

TripFunctions.register(app)
DashboardFunctions.register(app)
HealthFunctions.register(app)
