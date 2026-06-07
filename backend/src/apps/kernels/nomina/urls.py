from __future__ import annotations

from django.urls import path

from .views import (
    HealthView,
    IRBracketView,
    NominaConfigDetailView,
    NominaConfigView,
    PayrollEntryView,
    PayrollPeriodView,
    PayrollSheetActionView,
    PayrollSheetPdfView,
    PayrollSheetView,
    PayrollSheetXlsxView,
)
from .views_field import (
    FieldApplyToSheetView,
    FieldApprovalApproveView,
    FieldApprovalRequestView,
    FieldConsolidateView,
    FieldConsolidationListView,
    FieldCrewReportView,
    FieldCrewView,
    FieldRollCallView,
    FieldTransferView,
    FieldWorkDayDetailView,
    FieldWorkDayView,
    FieldWorkerEventView,
)
from .views_inss import (
    EmployeeInssEnrollmentView,
    PeriodInssClassifyView,
    PeriodInssElectionView,
    PeriodInssResolveView,
)

urlpatterns = [
    path("health/", HealthView.as_view()),
    # Configuración de tasas
    path("config/", NominaConfigView.as_view()),
    path("config/<int:config_id>/", NominaConfigDetailView.as_view()),
    path("config/<int:config_id>/ir-brackets/", IRBracketView.as_view()),
    # Períodos (quincenas)
    path("periods/", PayrollPeriodView.as_view()),
    # Planillas por período
    path("periods/<int:period_id>/sheets/", PayrollSheetView.as_view()),
    # Export legal (xlsx) — antes de la ruta de acción para no colisionar
    path("periods/<int:period_id>/sheets/<int:sheet_id>/planilla.xlsx", PayrollSheetXlsxView.as_view()),
    path("periods/<int:period_id>/sheets/<int:sheet_id>/planilla.pdf", PayrollSheetPdfView.as_view()),
    path("periods/<int:period_id>/sheets/<int:sheet_id>/<str:action>/", PayrollSheetActionView.as_view()),
    # Entradas por planilla
    path("periods/<int:period_id>/sheets/<int:sheet_id>/entries/", PayrollEntryView.as_view()),
    # Asistencia de campo — flujo diario
    path("field/work-days/", FieldWorkDayView.as_view()),
    path("field/work-days/<int:work_day_id>/", FieldWorkDayDetailView.as_view()),
    path("field/work-days/<int:work_day_id>/rollcall/", FieldRollCallView.as_view()),
    path("field/work-days/<int:work_day_id>/crews/", FieldCrewView.as_view()),
    path("field/work-days/<int:work_day_id>/events/", FieldWorkerEventView.as_view()),
    path("field/work-days/<int:work_day_id>/transfers/", FieldTransferView.as_view()),
    path("field/work-days/<int:work_day_id>/consolidate/", FieldConsolidateView.as_view()),
    path("field/work-days/<int:work_day_id>/consolidations/", FieldConsolidationListView.as_view()),
    # Aprobación SoD (maker-checker): solicitar → aprobar (approver != maker)
    path("field/work-days/<int:work_day_id>/approve-request/", FieldApprovalRequestView.as_view()),
    path("field/approvals/<uuid:request_id>/approve/", FieldApprovalApproveView.as_view()),
    path("field/crews/<int:crew_id>/report/", FieldCrewReportView.as_view()),
    path("field/sheets/<int:sheet_id>/apply-field-attendance/", FieldApplyToSheetView.as_view()),
    # Régimen INSS — afiliación fechada + elección por período
    path("inss/employees/<int:employee_id>/enrollments/", EmployeeInssEnrollmentView.as_view()),
    path("periods/<int:period_id>/inss/elections/", PeriodInssElectionView.as_view()),
    path("periods/<int:period_id>/inss/resolve/", PeriodInssResolveView.as_view()),
    path("periods/<int:period_id>/inss/classify/", PeriodInssClassifyView.as_view()),
]
