from __future__ import annotations

import pytest
from django.urls import resolve
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_api_v1_mounts_canonical_public_routes() -> None:
    client = APIClient()

    fuel = client.get("/api/v1/fuel/health/")
    assert fuel.status_code == 200
    assert fuel.headers.get("Deprecation") is None

    bootstrap = client.get("/api/v1/auth/bootstrap/status/")
    assert bootstrap.status_code == 200


def test_api_v1_does_not_mount_retired_legacy_hmac_route() -> None:
    response = APIClient().post("/api/v1/sync-hmac/batch/", data={}, format="json")
    assert response.status_code == 404


def test_api_v1_mounts_nomina_field_attendance_routes() -> None:
    expected_views = {
        "/api/v1/nomina/field/work-days/": "FieldWorkDayView",
        "/api/v1/nomina/field/capture/work-days/": "FieldCaptureWorkDayView",
        "/api/v1/nomina/field/crews/": "FieldCaptureCrewView",
        "/api/v1/nomina/field/reports/1/events/": "FieldCaptureEventView",
        "/api/v1/nomina/field/reports/1/build-attendance/": "FieldReportBuildAttendanceView",
    }

    for path, view_name in expected_views.items():
        match = resolve(path)
        assert getattr(match.func, "view_class").__name__ == view_name


def test_api_v1_mounts_sync_v2_batch_route() -> None:
    match = resolve("/api/v1/sync/batch/")
    assert getattr(match.func, "view_class").__name__ == "SyncBatchView"
