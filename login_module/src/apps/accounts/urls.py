from django.urls import path

from .views import (
    LoginView,
    LogoutView,
    MeACLView,
    MeView,
    RefreshView,
    BootstrapStatusView,
    BootstrapInitView,
    BootstrapOrgView,
    PasswordChangeView,
)

urlpatterns = [
    path("login/", LoginView.as_view(), name="auth-login"),
    path("refresh/", RefreshView.as_view(), name="auth-refresh"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    path("me/", MeView.as_view(), name="auth-me"),
    path("me/acl/", MeACLView.as_view(), name="me-acl"),

    # Onboarding / bootstrap
    path("bootstrap/status/", BootstrapStatusView.as_view(), name="auth-bootstrap-status"),
    path("bootstrap/init/", BootstrapInitView.as_view(), name="auth-bootstrap-init"),
    path("bootstrap/org/", BootstrapOrgView.as_view(), name="auth-bootstrap-org"),

    # Password change (forzado)
    path("password/", PasswordChangeView.as_view(), name="auth-password-change"),
]
