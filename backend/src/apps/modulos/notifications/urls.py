from __future__ import annotations

from django.urls import path

from .views import DeviceTokenView, HealthView

app_name = "notifications"

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("device-token/", DeviceTokenView.as_view(), name="device-token"),
]
