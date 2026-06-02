from __future__ import annotations

from django.urls import path

from .views import (
    AdjustView,
    BalanceView,
    HealthView,
    IssueView,
    ItemView,
    KardexView,
    LotCreateView,
    LotListView,
    LotStockView,
    ReceiveView,
    StockSummaryView,
    TransferView,
    WarehouseView,
)


urlpatterns = [
    path("health/", HealthView.as_view()),
    # Warehouses: GET=list, POST=create (backward compat con tests y código existente)
    path("warehouses/", WarehouseView.as_view()),
    # Items: GET=list, POST=create (backward compat)
    path("items/", ItemView.as_view()),
    # Lots
    path("lots/", LotListView.as_view()),
    path("lots/create/", LotCreateView.as_view()),
    # Stock
    path("stock/", StockSummaryView.as_view()),        # paginado, filtros avanzados
    path("balances/", BalanceView.as_view()),           # backward compat: ?warehouse_id=X&item_id=Y
    path("stock/lots/", LotStockView.as_view()),
    path("kardex/", KardexView.as_view()),
    # Movement commands
    path("movements/receive/", ReceiveView.as_view()),
    path("movements/issue/", IssueView.as_view()),
    path("movements/adjust/", AdjustView.as_view()),
    path("transfers/", TransferView.as_view()),
]
