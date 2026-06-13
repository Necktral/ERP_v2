from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.HealthView.as_view()),
    path("settings/", views.SettingsView.as_view()),
    path("exchange-rates/", views.ExchangeRateView.as_view()),
    path("producers/", views.ProducerListCreateView.as_view()),
    path("producers/<int:producer_id>/deposit/", views.ProducerDepositView.as_view()),
    path("qualities/", views.QualityListCreateView.as_view()),
    path("applications/", views.ApplicationListCreateView.as_view()),
    path("applications/<int:application_id>/submit/", views.ApplicationSubmitView.as_view()),
    path("applications/<int:application_id>/approve/", views.ApplicationApproveView.as_view()),
    path("applications/<int:application_id>/reject/", views.ApplicationRejectView.as_view()),
    path("applications/<int:application_id>/disburse/", views.ApplicationDisburseView.as_view()),
    path("loans/", views.LoanListView.as_view()),
    path("loans/<int:loan_id>/statement/", views.LoanStatementView.as_view()),
    path("loans/<int:loan_id>/payments/", views.LoanPaymentView.as_view()),
    path("receptions/", views.ReceptionListCreateView.as_view()),
    path("fixations/", views.FixationListCreateView.as_view()),
    path("liquidations/", views.LiquidationListCreateView.as_view()),
]
