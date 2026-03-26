from __future__ import annotations

from rest_framework.test import APIClient


def test_fuel_legacy_aliases_emit_deprecation_headers() -> None:
    client = APIClient()

    for prefix in ("/api/backend/fuel/", "/api/backend/estacion-servicios/"):
        response = client.get(f"{prefix}health/")
        assert response.status_code == 200
        assert response.headers.get("Deprecation") == "true"
        assert response.headers.get("Link") == "</api/fuel/>; rel=\"successor-version\""


def test_fuel_canonical_does_not_emit_legacy_headers() -> None:
    client = APIClient()
    response = client.get("/api/fuel/health/")

    assert response.status_code == 200
    assert response.headers.get("Deprecation") is None
    assert response.headers.get("Sunset") is None
    assert response.headers.get("Link") is None


def test_billing_legacy_lane_emits_deprecation_headers() -> None:
    client = APIClient()
    response = client.get("/api/legacy/billing/health-legacy/")

    assert response.status_code == 200
    assert response.headers.get("Deprecation") == "true"
    assert response.headers.get("Link") == "</api/billing/>; rel=\"successor-version\""
