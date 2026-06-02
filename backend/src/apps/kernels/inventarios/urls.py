from __future__ import annotations

from django.urls import path

from .views import (
    AdjustView,
    HealthView,
    IssueView,
    ItemCreateView,
    ItemListView,
    KardexView,
    LotCreateView,
    LotListView,
    LotStockView,
    ReceiveView,
    StockSummaryView,
    TransferView,
    WarehouseCreateView,
    WarehouseListView,
)


urlpatterns = [
    path("health/", HealthView.as_view()),
    # Warehouses
    path("warehouses/", WarehouseListView.as_view()),
    path("warehouses/create/", WarehouseCreateView.as_view()),
    # Items
    path("items/", ItemListView.as_view()),
    path("items/create/", ItemCreateView.as_view()),
    # Lots
    path("lots/", LotListView.as_view()),
    path("lots/create/", LotCreateView.as_view()),
    # Stock
    path("stock/", StockSummaryView.as_view()),
    path("stock/lots/", LotStockView.as_view()),
    path("kardex/", KardexView.as_view()),
    # Movement commands
    path("movements/receive/", ReceiveView.as_view()),
    path("movements/issue/", IssueView.as_view()),
    path("movements/adjust/", AdjustView.as_view()),
    path("transfers/", TransferView.as_view()),
]
