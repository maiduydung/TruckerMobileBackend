"""Health check and CORS preflight endpoints."""
import datetime
import logging

import azure.functions as func

from services.response import ResponseHelper

logger = logging.getLogger(__name__)


class HealthFunctions:
    """Registers health and utility endpoints."""

    @staticmethod
    def register(app: func.FunctionApp):
        """Bind health and CORS routes to the function app."""

        @app.function_name(name="health")
        @app.route(route="health", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
        def health(req: func.HttpRequest) -> func.HttpResponse:
            """Return API health status."""
            return ResponseHelper.json({
                "status": "ok",
                "service": "NhuTin Trucker API",
                "time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            })

        @app.function_name(name="cors_preflight")
        @app.route(route="{*path}", methods=["OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
        def cors_preflight(req: func.HttpRequest) -> func.HttpResponse:
            """Handle CORS preflight requests for all routes."""
            return ResponseHelper.preflight()


def main():
    """Test health module loads correctly."""
    print("HealthFunctions module loaded OK")


if __name__ == "__main__":
    main()
