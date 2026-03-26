"""HTTP response helpers and CORS configuration."""
import json

import azure.functions as func

ALLOWED_ORIGINS = {
    "http://localhost:8081",
    "http://localhost:19006",
    "http://localhost:3000",
    "http://localhost:5173",
}


class ResponseHelper:
    """Builds Azure Function HTTP responses with CORS headers."""

    @staticmethod
    def cors_headers(origin: str = "*") -> dict:
        """Generate CORS headers, matching origin if in allowlist."""
        return {
            "Access-Control-Allow-Origin": origin if origin in ALLOWED_ORIGINS else "*",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        }

    @classmethod
    def json(cls, body: dict, status_code: int = 200) -> func.HttpResponse:
        """Return a JSON response with CORS headers."""
        return func.HttpResponse(
            json.dumps(body, default=str),
            status_code=status_code,
            headers={
                "Content-Type": "application/json",
                **cls.cors_headers(),
            },
        )

    @classmethod
    def preflight(cls) -> func.HttpResponse:
        """Handle CORS preflight (OPTIONS) requests."""
        return func.HttpResponse(status_code=204, headers=cls.cors_headers())


def main():
    """Test response helper output."""
    resp = ResponseHelper.json({"status": "ok", "test": True})
    print(f"Status: {resp.status_code}")
    print(f"Headers: {dict(resp.headers)}")
    print(f"Body: {resp.get_body().decode()}")


if __name__ == "__main__":
    main()
