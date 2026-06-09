from django.urls import path

from .views import GroupCarteraView, IntercompanyChargeView

urlpatterns = [
    path("charges/", IntercompanyChargeView.as_view(), name="intercompany-charges"),
    path("group-cartera/", GroupCarteraView.as_view(), name="intercompany-group-cartera"),
]
