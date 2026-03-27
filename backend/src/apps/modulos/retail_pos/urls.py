from __future__ import annotations

from django.urls import path

from .views import (
    HealthView,
    PosOperationalCockpitView,
    PosPeripheralCapabilitiesView,
    PosPeripheralEdgeChallengeView,
    PosPeripheralEdgeHandshakeView,
    PosPeripheralStatusView,
    PosSessionCloseView,
    PosSessionCurrentView,
    PosSessionOpenView,
    PosTicketCompensationRetryView,
    PosTicketCheckoutView,
    PosTicketListCreateView,
    PosTicketVoidView,
)

urlpatterns = [
    path("health/", HealthView.as_view(), name="retail-pos-health"),
    path("sessions/current/", PosSessionCurrentView.as_view(), name="retail-pos-session-current"),
    path("sessions/open/", PosSessionOpenView.as_view(), name="retail-pos-session-open"),
    path("sessions/<int:session_id>/close/", PosSessionCloseView.as_view(), name="retail-pos-session-close"),
    path("tickets/", PosTicketListCreateView.as_view(), name="retail-pos-ticket-list-create"),
    path("tickets/<int:ticket_id>/checkout/", PosTicketCheckoutView.as_view(), name="retail-pos-ticket-checkout"),
    path(
        "tickets/<int:ticket_id>/compensate/retry/",
        PosTicketCompensationRetryView.as_view(),
        name="retail-pos-ticket-compensation-retry",
    ),
    path("checkouts/<int:ticket_id>/", PosTicketCheckoutView.as_view(), name="retail-pos-checkout-alias"),
    path("voids/<int:ticket_id>/", PosTicketVoidView.as_view(), name="retail-pos-void-alias"),
    path("peripherals/status/", PosPeripheralStatusView.as_view(), name="retail-pos-peripherals-status"),
    path("peripherals/capabilities/", PosPeripheralCapabilitiesView.as_view(), name="retail-pos-peripherals-capabilities"),
    path("peripherals/edge/challenge/", PosPeripheralEdgeChallengeView.as_view(), name="retail-pos-edge-challenge"),
    path("peripherals/edge/handshake/", PosPeripheralEdgeHandshakeView.as_view(), name="retail-pos-edge-handshake"),
    path("cockpit/", PosOperationalCockpitView.as_view(), name="retail-pos-cockpit"),
]
