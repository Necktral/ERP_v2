from django.urls import path

from modulos.estacion_servicios.views import FuelHealthView

urlpatterns = [
    path("health/", FuelHealthView.as_view(), name="fuel-health"),
]
