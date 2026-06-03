from django.urls import path

from .views import InventoryReadDemoView
from .views import (
    AssignmentListCreateView,
    AssignmentRevokeView,
    PermissionListView,
    RoleListView,
    UserEffectivePermissionsView,
)

urlpatterns = [
    path("demo/inventory-read/", InventoryReadDemoView.as_view(), name="demo-inventory-read"),
    path("roles/", RoleListView.as_view(), name="role-list"),
    path("permissions/", PermissionListView.as_view(), name="permission-list"),
    path("assignments/", AssignmentListCreateView.as_view(), name="assignment-list-create"),
    path("assignments/<int:assignment_id>/revoke/", AssignmentRevokeView.as_view(), name="assignment-revoke"),
    path("users/<int:user_id>/effective-permissions/", UserEffectivePermissionsView.as_view(), name="user-effective-permissions"),
]
