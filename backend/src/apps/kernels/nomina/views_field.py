"""Endpoints HTTP del flujo diario de asistencia de campo.

Capa delgada sobre `services.py`: abrir día → pase de lista → cuadrillas/reportes →
eventos/traslados → consolidar → aprobar → aplicar a planilla. Toda la regla de
dominio (SoD, scope, validaciones) vive en los servicios; aquí solo se resuelven
ids a objetos con scope de empresa y se traduce `FieldAttendanceError` a HTTP 400.

Se monta en `api/nomina/field/...` (esquema actual). Cuando Codex aterrice
`/api/v1/`, el prefijo global se reubica sin tocar estas rutas relativas.
"""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.modulos.common.domain_errors import DomainError
from apps.modulos.common.pagination import get_limit_offset, paginate_queryset as _paginate
from apps.modulos.common.permissions import rbac_permission
from apps.modulos.hr.models import Employee
from apps.modulos.iam.approvals import (
    ApprovalStateError,
    ApproverNotAuthorizedError,
    SelfApprovalError,
)
from apps.modulos.iam.models import ApprovalRequest, OrgUnit

from .field_sod import (
    FIELD_ATTENDANCE_APPROVE_ACTION,
    approve_field_attendance_with_sod,
    request_field_attendance_approval,
)
from .models import (
    FieldAttendanceConsolidation,
    FieldCrew,
    FieldCrewReport,
    FieldWorkDay,
    PayrollPeriod,
    PayrollSheet,
)
from .serializers import (
    FieldAttendanceConsolidationOut,
    FieldConsolidateIn,
    FieldCrewCreateIn,
    FieldCrewReportIn,
    FieldRollCallIn,
    FieldTransferIn,
    FieldWorkDayCreateIn,
    FieldWorkDayOut,
    FieldWorkerEventIn,
)
from .services import (
    apply_field_attendance_to_sheet,
    consolidate_field_attendance,
    create_field_crew,
    open_field_work_day,
    record_worker_event,
    submit_crew_report,
    submit_rollcall,
    transfer_worker,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _domain_error(exc: ValueError) -> Response:
    """Traduce FieldAttendanceError (o cualquier ValueError de dominio) a 400."""
    payload: dict = {"detail": str(exc)}
    code = getattr(exc, "code", None)
    if code:
        payload["code"] = code
    ctx = getattr(exc, "context", None)
    if ctx:
        payload["context"] = ctx
    return Response(payload, status=status.HTTP_400_BAD_REQUEST)


def _approval_error(exc: DomainError) -> Response:
    """Mapea los errores del maker-checker SoD a su HTTP."""
    if isinstance(exc, (SelfApprovalError, ApproverNotAuthorizedError)):
        http = status.HTTP_403_FORBIDDEN
    elif isinstance(exc, ApprovalStateError):
        http = status.HTTP_409_CONFLICT
    else:
        http = status.HTTP_400_BAD_REQUEST
    payload: dict = {"detail": str(exc)}
    code = getattr(exc, "code", None)
    if code:
        payload["code"] = code
    return Response(payload, status=http)


def _employee(company: OrgUnit, employee_id: int) -> Employee:
    return get_object_or_404(Employee, id=employee_id, company=company)


def _work_day(company: OrgUnit, work_day_id: int) -> FieldWorkDay:
    return get_object_or_404(FieldWorkDay, id=work_day_id, company=company)


def _crew(work_day: FieldWorkDay, crew_id: int) -> FieldCrew:
    return get_object_or_404(FieldCrew, id=crew_id, work_day=work_day)


def _work_day_response(work_day: FieldWorkDay, *, created: bool = False, extra: dict | None = None):
    work_day.refresh_from_db()
    data = FieldWorkDayOut(work_day).data
    if extra:
        data = {**data, **extra}
    return Response(data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Día de campo — abrir / listar / detalle
# ---------------------------------------------------------------------------

class FieldWorkDayView(APIView):
    """GET → listar días de campo   POST → abrir día"""

    def get_permissions(self):
        if self.request.method == "POST":
            return [rbac_permission("nomina.field.capture")()]
        return [rbac_permission("nomina.field.read")()]

    def get(self, request):
        company: OrgUnit = request.company
        qs = FieldWorkDay.objects.filter(company=company).order_by("-work_date", "-id")
        st = request.query_params.get("status")
        if st:
            qs = qs.filter(status=st)
        work_date = request.query_params.get("work_date")
        if work_date:
            qs = qs.filter(work_date=work_date)
        branch_id = request.query_params.get("branch_id")
        if branch_id:
            qs = qs.filter(branch_id=branch_id)
        limit, offset = get_limit_offset(request)
        total, rows = _paginate(qs, limit=limit, offset=offset)
        return Response({"count": total, "limit": limit, "offset": offset, "results": FieldWorkDayOut(rows, many=True).data})

    def post(self, request):
        company: OrgUnit = request.company
        s = FieldWorkDayCreateIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data

        branch = None
        if v.get("branch_id"):
            branch = get_object_or_404(OrgUnit, id=v["branch_id"], parent=company)
        period = None
        if v.get("payroll_period_id"):
            period = get_object_or_404(PayrollPeriod, id=v["payroll_period_id"], company=company)

        try:
            work_day = open_field_work_day(
                request=request, actor=request.user, company=company,
                work_date=v["work_date"], branch=branch, payroll_period=period,
                notes=v.get("notes", ""),
            )
        except ValueError as exc:
            return _domain_error(exc)
        return _work_day_response(work_day, created=True)


class FieldWorkDayDetailView(APIView):
    """GET → detalle de un día de campo"""

    permission_classes = [rbac_permission("nomina.field.read")]

    def get(self, request, work_day_id):
        work_day = _work_day(request.company, work_day_id)
        return Response(FieldWorkDayOut(work_day).data)


# ---------------------------------------------------------------------------
# Captura — pase de lista, cuadrillas, reportes, eventos, traslados
# ---------------------------------------------------------------------------

class FieldRollCallView(APIView):
    """POST → pase de lista inicial del día"""

    permission_classes = [rbac_permission("nomina.field.capture")]

    def post(self, request, work_day_id):
        company: OrgUnit = request.company
        work_day = _work_day(company, work_day_id)
        s = FieldRollCallIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data

        lines = [
            {
                "employee": _employee(company, line["employee_id"]),
                "status": line.get("status", ""),
                "absence_reason": line.get("absence_reason", ""),
                "note": line.get("note", ""),
            }
            for line in v["lines"]
        ]
        try:
            rollcall = submit_rollcall(
                request=request, actor=request.user, work_day=work_day,
                lines=lines, notes=v.get("notes", ""),
            )
        except ValueError as exc:
            return _domain_error(exc)
        return _work_day_response(work_day, created=True, extra={"rollcall_id": rollcall.id})


class FieldCrewView(APIView):
    """POST → crear cuadrilla del día"""

    permission_classes = [rbac_permission("nomina.field.capture")]

    def post(self, request, work_day_id):
        company: OrgUnit = request.company
        work_day = _work_day(company, work_day_id)
        s = FieldCrewCreateIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        supervisor = _employee(company, v["supervisor_employee_id"])
        try:
            crew = create_field_crew(
                request=request, actor=request.user, work_day=work_day,
                name=v["name"], supervisor_employee=supervisor,
            )
        except ValueError as exc:
            return _domain_error(exc)
        return Response(
            {"id": crew.id, "name": crew.name, "work_day_id": work_day.id,
             "supervisor_employee_id": supervisor.id},
            status=status.HTTP_201_CREATED,
        )


class FieldCrewReportView(APIView):
    """POST → reporte diario de una cuadrilla"""

    permission_classes = [rbac_permission("nomina.field.capture")]

    def post(self, request, crew_id):
        company: OrgUnit = request.company
        crew = get_object_or_404(FieldCrew, id=crew_id, work_day__company=company)
        s = FieldCrewReportIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data

        lines = [
            {
                "employee": _employee(company, line["employee_id"]),
                "event_type": line.get("event_type", ""),
                "day_value": line.get("day_value"),
                "notes": line.get("notes", ""),
            }
            for line in v["lines"]
        ]
        try:
            report = submit_crew_report(
                request=request, actor=request.user, crew=crew, lines=lines,
                labor_code=v.get("labor_code", ""), labor_name=v.get("labor_name", ""),
                zone_label=v.get("zone_label", ""), notes=v.get("notes", ""),
            )
        except ValueError as exc:
            return _domain_error(exc)
        return Response(
            {"id": report.id, "crew_id": crew.id, "status": report.status,
             "work_day_status": crew.work_day.status},
            status=status.HTTP_201_CREATED,
        )


class FieldWorkerEventView(APIView):
    """POST → novedad individual de un trabajador"""

    permission_classes = [rbac_permission("nomina.field.capture")]

    def post(self, request, work_day_id):
        company: OrgUnit = request.company
        work_day = _work_day(company, work_day_id)
        s = FieldWorkerEventIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        employee = _employee(company, v["employee_id"])
        crew_report = None
        if v.get("crew_report_id"):
            crew_report = get_object_or_404(
                FieldCrewReport, id=v["crew_report_id"], crew__work_day=work_day
            )
        try:
            event = record_worker_event(
                request=request, actor=request.user, work_day=work_day, employee=employee,
                event_type=v["event_type"], details=v.get("details", ""),
                crew_report=crew_report, occurred_at=v.get("occurred_at"),
            )
        except ValueError as exc:
            return _domain_error(exc)
        return Response(
            {"id": event.id, "work_day_id": work_day.id, "employee_id": employee.id,
             "event_type": event.event_type},
            status=status.HTTP_201_CREATED,
        )


class FieldTransferView(APIView):
    """POST → traslado de un trabajador entre cuadrillas"""

    permission_classes = [rbac_permission("nomina.field.capture")]

    def post(self, request, work_day_id):
        company: OrgUnit = request.company
        work_day = _work_day(company, work_day_id)
        s = FieldTransferIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        employee = _employee(company, v["employee_id"])
        from_crew = _crew(work_day, v["from_crew_id"])
        to_crew = _crew(work_day, v["to_crew_id"])
        try:
            transfer = transfer_worker(
                request=request, actor=request.user, work_day=work_day, employee=employee,
                from_crew=from_crew, to_crew=to_crew, reason=v["reason"],
            )
        except ValueError as exc:
            return _domain_error(exc)
        return Response(
            {"id": transfer.id, "work_day_id": work_day.id, "employee_id": employee.id,
             "from_crew_id": from_crew.id, "to_crew_id": to_crew.id},
            status=status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# Consolidación, aprobación y aplicación a planilla
# ---------------------------------------------------------------------------

class FieldConsolidateView(APIView):
    """POST → consolida el estado por empleado/día"""

    permission_classes = [rbac_permission("nomina.field.consolidate")]

    def post(self, request, work_day_id):
        company: OrgUnit = request.company
        work_day = _work_day(company, work_day_id)
        s = FieldConsolidateIn(data=request.data)
        s.is_valid(raise_exception=True)
        period = None
        if s.validated_data.get("payroll_period_id"):
            period = get_object_or_404(
                PayrollPeriod, id=s.validated_data["payroll_period_id"], company=company
            )
        try:
            consolidations = consolidate_field_attendance(
                request=request, actor=request.user, work_day=work_day, payroll_period=period,
            )
        except ValueError as exc:
            return _domain_error(exc)
        return _work_day_response(
            work_day, extra={"consolidations": FieldAttendanceConsolidationOut(consolidations, many=True).data}
        )


class FieldApprovalRequestView(APIView):
    """POST → maker: solicita la aprobación de la consolidación del día (SoD)."""

    permission_classes = [rbac_permission("nomina.field.approve.request")]

    def post(self, request, work_day_id):
        company: OrgUnit = request.company
        work_day = _work_day(company, work_day_id)
        try:
            approval = request_field_attendance_approval(
                request=request, actor=request.user, work_day=work_day,
                reason=request.data.get("reason", "") or "",
                idempotency_key=request.data.get("idempotency_key", "") or "",
            )
        except ValueError as exc:
            return _domain_error(exc)
        except DomainError as exc:
            return _approval_error(exc)
        return Response(
            {"approval_request_id": str(approval.request_id), "status": approval.status,
             "work_day_id": work_day.id},
            status=status.HTTP_202_ACCEPTED,
        )


class FieldApprovalApproveView(APIView):
    """POST → checker: aprueba (SoD approver != maker) y ejecuta la aprobación del día."""

    permission_classes = [rbac_permission("nomina.field.approve")]

    def post(self, request, request_id):
        company: OrgUnit = request.company
        approval = ApprovalRequest.objects.filter(
            request_id=request_id, company=company, action_type=FIELD_ATTENDANCE_APPROVE_ACTION,
        ).first()
        if approval is None:
            return Response({"detail": "Solicitud de aprobación no encontrada."},
                            status=status.HTTP_404_NOT_FOUND)
        try:
            consolidations = approve_field_attendance_with_sod(
                request=request, approver=request.user, approval=approval,
            )
        except ValueError as exc:
            return _domain_error(exc)
        except DomainError as exc:
            return _approval_error(exc)
        work_day = FieldWorkDay.objects.get(id=int((approval.payload or {}).get("work_day_id")))
        return _work_day_response(
            work_day, extra={"consolidations": FieldAttendanceConsolidationOut(consolidations, many=True).data}
        )


class FieldConsolidationListView(APIView):
    """GET → consolidaciones de un día de campo"""

    permission_classes = [rbac_permission("nomina.field.read")]

    def get(self, request, work_day_id):
        work_day = _work_day(request.company, work_day_id)
        qs = FieldAttendanceConsolidation.objects.filter(work_day=work_day).select_related("work_day").order_by("employee_id")
        return Response({"results": FieldAttendanceConsolidationOut(qs, many=True).data})


class FieldApplyToSheetView(APIView):
    """POST → aplica la asistencia aprobada a las líneas de una planilla"""

    permission_classes = [rbac_permission("nomina.field.apply")]

    def post(self, request, sheet_id):
        company: OrgUnit = request.company
        sheet = get_object_or_404(PayrollSheet, id=sheet_id, period__company=company)
        try:
            result = apply_field_attendance_to_sheet(
                request=request, actor=request.user, sheet=sheet,
            )
        except ValueError as exc:
            return _domain_error(exc)
        return Response(result)
