from __future__ import annotations

from django.urls import path

from .views import (
    HealthView,
    PurchaseDocDetailView,
    PurchaseDocListCreateView,
    PurchaseDocPostView,
    PurchaseDocVoidView,
)

urlpatterns = [
    path("health/", HealthView.as_view()),
    path("docs/", PurchaseDocListCreateView.as_view()),
    path("docs/<int:doc_id>/", PurchaseDocDetailView.as_view()),
    path("docs/<int:doc_id>/post/", PurchaseDocPostView.as_view()),
    path("docs/<int:doc_id>/void/", PurchaseDocVoidView.as_view()),
]
