from __future__ import annotations

from django.urls import path

from .views import (
    ApplyPlanView,
    AssetDetailView,
    AssetView,
    AssignDriverView,
    DocumentView,
    DriverView,
    HealthView,
    MaintenanceTypeView,
    PlanView,
    RecordMeterView,
    RuleView,
    RunAlertsView,
)

app_name = "fleet"

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("assets/", AssetView.as_view(), name="assets"),
    path("assets/<int:asset_id>/", AssetDetailView.as_view(), name="asset-detail"),
    path("drivers/", DriverView.as_view(), name="drivers"),
    path("driver-assignments/", AssignDriverView.as_view(), name="driver-assign"),
    path("meter-readings/", RecordMeterView.as_view(), name="meter-readings"),
    path("documents/", DocumentView.as_view(), name="documents"),
    path("maintenance/types/", MaintenanceTypeView.as_view(), name="maintenance-types"),
    path("maintenance/plans/", PlanView.as_view(), name="maintenance-plans"),
    path("maintenance/rules/", RuleView.as_view(), name="maintenance-rules"),
    path("maintenance/apply-plan/", ApplyPlanView.as_view(), name="maintenance-apply-plan"),
    path("alerts/run/", RunAlertsView.as_view(), name="alerts-run"),
]
