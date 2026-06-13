from django.urls import path

from .views import (
    PartyDetailView,
    PartyListCreateView,
    PartyRoleAssignView,
    PartyRoleRevokeView,
)

urlpatterns = [
    path("", PartyListCreateView.as_view(), name="party-list-create"),
    path("<int:party_id>/", PartyDetailView.as_view(), name="party-detail"),
    path("<int:party_id>/roles/", PartyRoleAssignView.as_view(), name="party-role-assign"),
    path("<int:party_id>/roles/revoke/", PartyRoleRevokeView.as_view(), name="party-role-revoke"),
]
