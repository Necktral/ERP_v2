from django.urls import path

from .views import (
    CompanyCostReportView,
    CompanyRealCostReportView,
    FieldLaborCostReportView,
    FieldReconciliationReportView,
    FincaCostPostView,
    FincaListView,
    FincaProfileView,
    FincaRealCostReportView,
    LaborListCreateView,
    PlotCostReportView,
    PlotDetailView,
    PlotListCreateView,
    WorkOrderDetailView,
    WorkOrderInsumoView,
    WorkOrderIssueInsumoView,
    WorkOrderListCreateView,
)
from .views_budget import (
    FincaBudgetApproveView,
    FincaBudgetArchiveView,
    FincaBudgetDetailView,
    FincaBudgetLinesView,
    FincaBudgetListCreateView,
    FincaBudgetVsActualView,
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
    path("work-orders/<int:work_order_id>/issue-insumo/", WorkOrderIssueInsumoView.as_view(), name="finca-work-order-issue-insumo"),
    path("reports/plot-cost/", PlotCostReportView.as_view(), name="finca-report-plot-cost"),
    path("reports/company-cost/", CompanyCostReportView.as_view(), name="finca-report-company-cost"),
    path("reports/field-labor-cost/", FieldLaborCostReportView.as_view(), name="finca-report-field-labor-cost"),
    path("reports/field-reconciliation/", FieldReconciliationReportView.as_view(), name="finca-report-field-reconciliation"),
    path("reports/finca-cost/", FincaRealCostReportView.as_view(), name="finca-report-finca-cost"),
    path("reports/finca-cost/post/", FincaCostPostView.as_view(), name="finca-report-finca-cost-post"),
    path("reports/company-real-cost/", CompanyRealCostReportView.as_view(), name="finca-report-company-real-cost"),
    # Presupuesto agrícola (Ola G)
    path("budgets/", FincaBudgetListCreateView.as_view(), name="finca-budget-list"),
    path("budgets/<int:budget_id>/", FincaBudgetDetailView.as_view(), name="finca-budget-detail"),
    path("budgets/<int:budget_id>/lines/", FincaBudgetLinesView.as_view(), name="finca-budget-lines"),
    path("budgets/<int:budget_id>/approve/", FincaBudgetApproveView.as_view(), name="finca-budget-approve"),
    path("budgets/<int:budget_id>/archive/", FincaBudgetArchiveView.as_view(), name="finca-budget-archive"),
    path("budgets/<int:budget_id>/vs-actual/", FincaBudgetVsActualView.as_view(), name="finca-budget-vs-actual"),
]
