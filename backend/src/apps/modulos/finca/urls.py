from django.urls import path

from .views import (
    CompanyCostReportView,
    CompanyRealCostReportView,
    FieldLaborCostReportView,
    FieldReconciliationReportView,
    FincaListView,
    FincaProfileView,
    FincaRealCostReportView,
    LaborListCreateView,
    PlotCostReportView,
    PlotDetailView,
    PlotListCreateView,
    WorkOrderDetailView,
    WorkOrderInsumoView,
    WorkOrderListCreateView,
)

urlpatterns = [
    path("fincas/", FincaListView.as_view(), name="finca-list"),
    path("fincas/<int:branch_id>/profile/", FincaProfileView.as_view(), name="finca-profile"),
    path("plots/", PlotListCreateView.as_view(), name="finca-plots"),
    path("plots/<int:plot_id>/", PlotDetailView.as_view(), name="finca-plot-detail"),
    path("labors/", LaborListCreateView.as_view(), name="finca-labors"),
    path("work-orders/", WorkOrderListCreateView.as_view(), name="finca-work-orders"),
    path("work-orders/<int:work_order_id>/", WorkOrderDetailView.as_view(), name="finca-work-order-detail"),
    path("work-orders/<int:work_order_id>/insumos/", WorkOrderInsumoView.as_view(), name="finca-work-order-insumos"),
    path("reports/plot-cost/", PlotCostReportView.as_view(), name="finca-report-plot-cost"),
    path("reports/company-cost/", CompanyCostReportView.as_view(), name="finca-report-company-cost"),
    path("reports/field-labor-cost/", FieldLaborCostReportView.as_view(), name="finca-report-field-labor-cost"),
    path("reports/field-reconciliation/", FieldReconciliationReportView.as_view(), name="finca-report-field-reconciliation"),
    path("reports/finca-cost/", FincaRealCostReportView.as_view(), name="finca-report-finca-cost"),
    path("reports/company-real-cost/", CompanyRealCostReportView.as_view(), name="finca-report-company-real-cost"),
]
