from __future__ import annotations

from rest_framework.test import APIClient


def test_fuel_canonical_and_alias_health_endpoints_are_available():
    client = APIClient()

    checks = [
        "/api/backend/estacion-servicios/health/",
        "/api/backend/fuel/health/",
        "/api/fuel/health/",
    ]

    for path in checks:
        response = client.get(path)
        assert response.status_code == 200
        assert response.data.get("module") == "fuel"


def test_fuel_legacy_alias_emits_deprecation_headers():
    client = APIClient()
    response = client.get("/api/fuel/health/")

    assert response.status_code == 200
    assert response.headers.get("Deprecation") == "true"
    assert "Mon, 18 May 2026" in (response.headers.get("Sunset") or "")
    assert "/api/backend/estacion-servicios/" in (response.headers.get("Link") or "")

