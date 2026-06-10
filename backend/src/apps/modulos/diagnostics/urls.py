from django.urls import path

from .views import (
    AIControlView,
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
    path("findings/", SecurityFindingListView.as_view(), name="diagnostics-finding-list"),
    path(
        "findings/<uuid:finding_id>/",
        SecurityFindingDetailView.as_view(),
        name="diagnostics-finding-detail",
    ),
    # Botón de apagado de la IA (kill switch runtime).
    path("ai-control/", AIControlView.as_view(), name="diagnostics-ai-control"),
]
