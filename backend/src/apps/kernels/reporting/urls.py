from __future__ import annotations

from django.urls import path

from .api.views import CatalogDetailView, CatalogListView, DatasetRunView, RunDetailView, RunsListView


urlpatterns = [
    path("catalog/", CatalogListView.as_view()),
    path("catalog/<str:dataset_key>/", CatalogDetailView.as_view()),
    path("datasets/<str:dataset_key>/run/", DatasetRunView.as_view()),
    path("runs/", RunsListView.as_view()),
    path("runs/<uuid:run_id>/", RunDetailView.as_view()),
]

