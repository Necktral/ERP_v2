from django.urls import path

from .views import ErrorEventDetailView, ErrorEventListView

urlpatterns = [
    path("errors/", ErrorEventListView.as_view(), name="diagnostics-error-list"),
    path(
        "errors/<uuid:error_id>/",
        ErrorEventDetailView.as_view(),
        name="diagnostics-error-detail",
    ),
]
