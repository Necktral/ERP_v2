from django.urls import path

from .views import (
    AIControlView,
    DiagnoseErrorView,
    DiagnosticRunDetailView,
    DiagnosticRunListView,
    ErrorEventDetailView,
    ErrorEventListView,
    SecurityFindingDetailView,
    SecurityFindingListView,
)

urlpatterns = [
    path("errors/", ErrorEventListView.as_view(), name="diagnostics-error-list"),
    path(
        "errors/<uuid:error_id>/",
        ErrorEventDetailView.as_view(),
        name="diagnostics-error-detail",
    ),
    # Causa raíz: dispara el diagnóstico determinista de un fallo.
    path(
        "errors/<uuid:error_id>/diagnose/",
        DiagnoseErrorView.as_view(),
        name="diagnostics-error-diagnose",
    ),
    path("diagnoses/", DiagnosticRunListView.as_view(), name="diagnostics-diagnosis-list"),
    path(
        "diagnoses/<uuid:run_id>/",
        DiagnosticRunDetailView.as_view(),
        name="diagnostics-diagnosis-detail",
    ),
    path("findings/", SecurityFindingListView.as_view(), name="diagnostics-finding-list"),
    path(
        "findings/<uuid:finding_id>/",
        SecurityFindingDetailView.as_view(),
        name="diagnostics-finding-detail",
    ),
    # Botón de apagado de la IA (kill switch runtime).
    path("ai-control/", AIControlView.as_view(), name="diagnostics-ai-control"),
]
