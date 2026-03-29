"""Tests for the HTTP response helper and CORS logic."""

import json
from services.response import ResponseHelper, ALLOWED_ORIGINS


class TestCorsHeaders:

    def test_allowed_origin_is_reflected(self):
        for origin in ALLOWED_ORIGINS:
            headers = ResponseHelper.cors_headers(origin)
            assert headers["Access-Control-Allow-Origin"] == origin

    def test_unknown_origin_gets_wildcard(self):
        headers = ResponseHelper.cors_headers("https://evil.com")
        assert headers["Access-Control-Allow-Origin"] == "*"

    def test_default_origin_is_wildcard(self):
        headers = ResponseHelper.cors_headers()
        assert headers["Access-Control-Allow-Origin"] == "*"

    def test_includes_methods(self):
        headers = ResponseHelper.cors_headers()
        assert "GET" in headers["Access-Control-Allow-Methods"]
        assert "POST" in headers["Access-Control-Allow-Methods"]
        assert "DELETE" in headers["Access-Control-Allow-Methods"]
        assert "OPTIONS" in headers["Access-Control-Allow-Methods"]

    def test_includes_content_type_header(self):
        headers = ResponseHelper.cors_headers()
        assert "Content-Type" in headers["Access-Control-Allow-Headers"]


class TestJsonResponse:

    def test_status_code_default(self):
        resp = ResponseHelper.json({"ok": True})
        assert resp.status_code == 200

    def test_custom_status_code(self):
        resp = ResponseHelper.json({"error": "not found"}, status_code=404)
        assert resp.status_code == 404

    def test_body_is_valid_json(self):
        resp = ResponseHelper.json({"key": "value", "count": 42})
        body = json.loads(resp.get_body().decode())
        assert body["key"] == "value"
        assert body["count"] == 42

    def test_content_type_header(self):
        resp = ResponseHelper.json({"ok": True})
        assert resp.headers.get("Content-Type") == "application/json"


class TestPreflightResponse:

    def test_preflight_status_204(self):
        resp = ResponseHelper.preflight()
        assert resp.status_code == 204


class TestAllowedOrigins:

    def test_localhost_origins_only(self):
        for origin in ALLOWED_ORIGINS:
            assert "localhost" in origin

    def test_not_empty(self):
        assert len(ALLOWED_ORIGINS) > 0
