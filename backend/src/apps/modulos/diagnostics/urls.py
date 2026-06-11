from django.urls import path

from .views import (
    AIControlView,
    AIDiagnoseView,
    CodeUnitEvidenceListView,
    DiagnoseErrorView,
    DiagnosticRunDetailView,
    DiagnosticRunListView,
    ErrorEventDetailView,
    ErrorEventListView,
    ReleaseReadinessView,
    SecurityFindingDetailView,
    SecurityFindingListView,
    SupervisionView,
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
    # Motor IA advisory (rellena la hipótesis de causa) — detrás del kill switch.
    path(
        "diagnoses/<uuid:run_id>/ai-analyze/",
        AIDiagnoseView.as_view(),
        name="diagnostics-diagnosis-ai-analyze",
    ),
    # ¿La línea que falló está testeada? Evidencia de cobertura por línea.
    path(
        "code-evidence/",
        CodeUnitEvidenceListView.as_view(),
        name="diagnostics-code-evidence-list",
    ),
    path("findings/", SecurityFindingListView.as_view(), name="diagnostics-finding-list"),
    path(
        "findings/<uuid:finding_id>/",
        SecurityFindingDetailView.as_view(),
        name="diagnostics-finding-detail",
    ),
    # Gate de release: verdicto de bloqueo por C1 abierto.
    path(
        "release-readiness/",
        ReleaseReadinessView.as_view(),
        name="diagnostics-release-readiness",
    ),
    # Supervisión: la cola priorizada del "qué falla y por qué" (determinista).
    path("supervision/", SupervisionView.as_view(), name="diagnostics-supervision"),
    # Botón de apagado de la IA (kill switch runtime).
    path("ai-control/", AIControlView.as_view(), name="diagnostics-ai-control"),
]
