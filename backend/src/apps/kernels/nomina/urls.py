from __future__ import annotations

from django.urls import path

from .views import (
    HealthView,
    IRBracketView,
    NominaConfigDetailView,
    NominaConfigView,
    PayrollEntryView,
    PayrollPeriodView,
    PayrollSheetActionView,
    PayrollSheetView,
)

urlpatterns = [
    path("health/", HealthView.as_view()),
    # Configuración de tasas
    path("config/", NominaConfigView.as_view()),
    path("config/<int:config_id>/", NominaConfigDetailView.as_view()),
    path("config/<int:config_id>/ir-brackets/", IRBracketView.as_view()),
    # Períodos (quincenas)
    path("periods/", PayrollPeriodView.as_view()),
    # Planillas por período
    path("periods/<int:period_id>/sheets/", PayrollSheetView.as_view()),
    path("periods/<int:period_id>/sheets/<int:sheet_id>/<str:action>/", PayrollSheetActionView.as_view()),
    # Entradas por planilla
    path("periods/<int:period_id>/sheets/<int:sheet_id>/entries/", PayrollEntryView.as_view()),
]
