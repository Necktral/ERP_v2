from django.urls import path

from .views import (
    HealthView,
    ScannedDocumentDetailView,
    ScannedDocumentListView,
    ScannedDocumentReviewView,
    ScannedDocumentUploadView,
)

urlpatterns = [
    path("health/", HealthView.as_view(), name="documents-health"),
    path("scans/", ScannedDocumentListView.as_view(), name="documents-scan-list"),
    path("scans/upload/", ScannedDocumentUploadView.as_view(), name="documents-scan-upload"),
    path("scans/<int:pk>/", ScannedDocumentDetailView.as_view(), name="documents-scan-detail"),
    path("scans/<int:pk>/review/", ScannedDocumentReviewView.as_view(), name="documents-scan-review"),
]
