from __future__ import annotations

from django.urls import path

from .api.views import (
    CatalogDetailView,
    CatalogListView,
    DatasetRunView,
    ExportDetailView,
    RunDetailView,
    RunExportCreateView,
    RunsListView,
    SavedViewDetailView,
    SavedViewsListCreateView,
    SnapshotGenerateView,
    SnapshotsListView,
)


urlpatterns = [
    path("catalog/", CatalogListView.as_view()),
    path("catalog/<str:dataset_key>/", CatalogDetailView.as_view()),
    path("datasets/<str:dataset_key>/run/", DatasetRunView.as_view()),
    path("runs/", RunsListView.as_view()),
    path("runs/<uuid:run_id>/", RunDetailView.as_view()),
    path("runs/<uuid:run_id>/export/", RunExportCreateView.as_view()),
    path("exports/<uuid:export_id>/", ExportDetailView.as_view()),
    path("snapshots/", SnapshotsListView.as_view()),
    path("snapshots/generate/", SnapshotGenerateView.as_view()),
    path("saved-views/", SavedViewsListCreateView.as_view()),
    path("saved-views/<uuid:view_id>/", SavedViewDetailView.as_view()),
]
