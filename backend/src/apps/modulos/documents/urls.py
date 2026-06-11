from django.urls import path

from .views import (
    HealthView,
    ScannedDocumentDetailView,
    ScannedDocumentExtractView,
    ScannedDocumentListView,
    ScannedDocumentReviewView,
    ScannedDocumentUploadView,
)

urlpatterns = [
    path("health/", HealthView.as_view(), name="documents-health"),
    path("scans/", ScannedDocumentListView.as_view(), name="documents-scan-list"),
    path("scans/upload/", ScannedDocumentUploadView.as_view(), name="documents-scan-upload"),
    path("scans/<int:pk>/", ScannedDocumentDetailView.as_view(), name="documents-scan-detail"),
    # Etapa F2 manual (re-extraer / rezagados); la cola de revisión = /scans/?status=EXTRACTED
    path("scans/<int:pk>/extract/", ScannedDocumentExtractView.as_view(), name="documents-scan-extract"),
    path("scans/<int:pk>/review/", ScannedDocumentReviewView.as_view(), name="documents-scan-review"),
]
