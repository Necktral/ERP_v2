from __future__ import annotations

from django.urls import path

from .views import (
    AccountDetailView,
    AccountListUpsertView,
    ApplyStoreCreditView,
    HealthView,
    SaleView,
)

app_name = "comisariato"

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("accounts/", AccountListUpsertView.as_view(), name="account-upsert"),
    path("accounts/<int:account_id>/", AccountDetailView.as_view(), name="account-detail"),
    path("sales/", SaleView.as_view(), name="sale"),
    path("payroll/<int:sheet_id>/apply-store-credit/", ApplyStoreCreditView.as_view(), name="apply-store-credit"),
]
