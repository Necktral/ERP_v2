from django.urls import path

from .views import (
    ControlFindingListView,
    ControlFindingResolveView,
    ControlScanView,
    SegregationRuleListView,
    SegregationViolationsView,
)

urlpatterns = [
    path("sod/rules/", SegregationRuleListView.as_view(), name="controls-sod-rules"),
    path("sod/violations/", SegregationViolationsView.as_view(), name="controls-sod-violations"),
    path("scan/", ControlScanView.as_view(), name="controls-scan"),
    path("findings/", ControlFindingListView.as_view(), name="controls-findings"),
    path("findings/<int:finding_id>/resolve/", ControlFindingResolveView.as_view(), name="controls-finding-resolve"),
]
