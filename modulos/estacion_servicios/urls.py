from django.urls import path

from modulos.estacion_servicios.views import (
    FuelDispenseCreateView,
    FuelHealthView,
    FuelSaleCreateView,
    FuelSaleCancelView,
    FuelShiftCloseView,
    FuelShiftOpenView,
    FuelUoMPreferencesView,
)

urlpatterns = [
    path("health/", FuelHealthView.as_view(), name="fuel-health"),
    path("shifts/open/", FuelShiftOpenView.as_view(), name="fuel-shift-open"),
    path("shifts/<int:shift_id>/close/", FuelShiftCloseView.as_view(), name="fuel-shift-close"),
    path("dispenses/", FuelDispenseCreateView.as_view(), name="fuel-dispense-create"),
    path("uom-preferences/", FuelUoMPreferencesView.as_view(), name="fuel-uom-preferences"),
    path("sales/", FuelSaleCreateView.as_view(), name="fuel-sale-create"),
    path("sales/<int:sale_id>/cancel/", FuelSaleCancelView.as_view(), name="fuel-sale-cancel"),
]
