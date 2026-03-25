from __future__ import annotations

from django.urls import path

from .views import EmbedTokenRedeemView, EmbedTokenView, WorkspaceListView


urlpatterns = [
    path("workspaces/", WorkspaceListView.as_view()),
    path("embed-token/", EmbedTokenView.as_view()),
    path("embed-token/redeem/", EmbedTokenRedeemView.as_view()),
]
