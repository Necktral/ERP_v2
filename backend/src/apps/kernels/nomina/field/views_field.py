from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.kernels.nomina.models import PayrollPeriod
from .serializers_field import (
    AttendanceReportOut,
    CrewCreateIn,
    CrewOut,
    FieldCaptureReportOut,
    FieldReportApprovalRequestIn,
    FieldReportApproveIn,
    FieldCaptureWorkDayCreateIn,
    FieldCaptureWorkDayOut,
    FieldCaptureEventCreateIn,
    FieldCaptureEventOut,
)
from apps.modulos.common.pagination import get_limit_offset, paginate_queryset as _paginate
from apps.modulos.common.permissions import rbac_permission
from apps.modulos.hr.models import Employee
from apps.modulos.iam.approvals import ApprovalStateError, ApproverNotAuthorizedError, SelfApprovalError
from apps.modulos.iam.models import ApprovalRequest, OrgUnit

from .models_field import Crew, FieldCaptureReport
from .services_field import (
    approve_report,
    build_attendance_report,
    create_crew,
    record_worker_event,
    request_report_approval,
    upsert_crew_report,
    upsert_work_day,
)


class FieldCaptureCrewView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [rbac_permission("nomina.field.manage")()]
        return [rbac_permission("nomina.field.read")()]

    def get(self, request):
        company: OrgUnit = request.company
        qs = Crew.objects.filter(company=company).order_by("name")
        branch_id = request.query_params.get("branch_id")
        if branch_id:
            qs = qs.filter(branch_id=int(branch_id))
        limit, offset = get_limit_offset(request)
        total, rows = _paginate(qs, limit=limit, offset=offset)
        return Response({"count": total, "limit": limit, "offset": offset, "results": CrewOut(rows, many=True).data})

    def post(self, request):
        company: OrgUnit = request.company
        s = CrewCreateIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        branch = get_object_or_404(OrgUnit, id=v["branch_id"], parent=company, unit_type=OrgUnit.UnitType.BRANCH)
        foreman = None
        if v.get("foreman_id"):
            foreman = get_object_or_404(Employee, id=v["foreman_id"], company=company)
        try:
            crew = create_crew(
                request=request,
                actor=request.user,
                company=company,
                branch=branch,
                name=v["name"],
                code=v.get("code", ""),
                foreman=foreman,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(CrewOut(crew).data, status=status.HTTP_201_CREATED)


class FieldCaptureWorkDayView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [rbac_permission("nomina.field.capture")()]
        return [rbac_permission("nomina.field.read")()]

    def get(self, request):
        company: OrgUnit = request.company
        qs = FieldCaptureReport.objects.filter(company=company).select_related("work_day", "crew").order_by("-created_at")
        period_id = request.query_params.get("period_id")
        if period_id:
            qs = qs.filter(period_id=int(period_id))
        crew_id = request.query_params.get("crew_id")
        if crew_id:
            qs = qs.filter(crew_id=int(crew_id))
        limit, offset = get_limit_offset(request)
        total, rows = _paginate(qs, limit=limit, offset=offset)
        return Response({"count": total, "limit": limit, "offset": offset, "results": FieldCaptureReportOut(rows, many=True).data})

    def post(self, request):
        company: OrgUnit = request.company
        s = FieldCaptureWorkDayCreateIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        period = get_object_or_404(PayrollPeriod, id=v["period_id"], company=company)
        crew = get_object_or_404(Crew, id=v["crew_id"], company=company, is_active=True)
        try:
            work_day = upsert_work_day(
                request=request,
                actor=request.user,
                period=period,
                crew=crew,
                work_date=v["work_date"],
                notes=v.get("notes", ""),
            )
            report = upsert_crew_report(
                request=request,
                actor=request.user,
                work_day=work_day,
                observations=v.get("observations", ""),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        payload = {"work_day": FieldCaptureWorkDayOut(work_day).data, "report": FieldCaptureReportOut(report).data}
        return Response(payload, status=status.HTTP_201_CREATED)


class FieldCaptureEventView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [rbac_permission("nomina.field.capture")()]
        return [rbac_permission("nomina.field.read")()]

    def get(self, request, report_id: int):
        company: OrgUnit = request.company
        report = get_object_or_404(FieldCaptureReport, id=report_id, company=company)
        qs = report.worker_events.order_by("employee_name", "cedula", "id")
        limit, offset = get_limit_offset(request)
        total, rows = _paginate(qs, limit=limit, offset=offset)
        return Response({"count": total, "limit": limit, "offset": offset, "results": FieldCaptureEventOut(rows, many=True).data})

    def post(self, request, report_id: int):
        company: OrgUnit = request.company
        report = get_object_or_404(FieldCaptureReport, id=report_id, company=company)
        s = FieldCaptureEventCreateIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        employee = None
        if v.get("employee_id"):
            employee = get_object_or_404(Employee, id=v["employee_id"], company=company)
        to_crew = None
        if v.get("to_crew_id"):
            to_crew = get_object_or_404(Crew, id=v["to_crew_id"], company=company, is_active=True)
        try:
            event = record_worker_event(
                request=request,
                actor=request.user,
                report=report,
                employee=employee,
                cedula=v.get("cedula", ""),
                employee_name=v.get("employee_name", ""),
                event_type=v["event_type"],
                day_value=v.get("day_value"),
                overtime_hours=v.get("overtime_hours"),
                sunday_worked_days=v.get("sunday_worked_days", 0),
                to_crew=to_crew,
                notes=v.get("notes", ""),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(FieldCaptureEventOut(event).data, status=status.HTTP_201_CREATED)


class FieldReportApprovalRequestView(APIView):
    permission_classes = [rbac_permission("nomina.attendance.review")]

    def post(self, request, report_id: int):
        company: OrgUnit = request.company
        report = get_object_or_404(FieldCaptureReport, id=report_id, company=company)
        s = FieldReportApprovalRequestIn(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            approval = request_report_approval(
                request=request,
                actor=request.user,
                report=report,
                reason=s.validated_data.get("reason", ""),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        report.refresh_from_db()
        return Response(
            {"approval_request_id": str(approval.request_id), "report": FieldCaptureReportOut(report).data},
            status=status.HTTP_201_CREATED,
        )


class FieldReportApproveView(APIView):
    permission_classes = [rbac_permission("nomina.attendance.approve")]

    def post(self, request, report_id: int):
        company: OrgUnit = request.company
        report = get_object_or_404(FieldCaptureReport, id=report_id, company=company)
        s = FieldReportApproveIn(data=request.data)
        s.is_valid(raise_exception=True)
        approval = get_object_or_404(ApprovalRequest, request_id=s.validated_data["approval_request_id"], company=company)
        try:
            report = approve_report(
                request=request,
                approver=request.user,
                report=report,
                approval=approval,
                note=s.validated_data.get("note", ""),
            )
        except (SelfApprovalError, ApproverNotAuthorizedError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except ApprovalStateError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(FieldCaptureReportOut(report).data)


class FieldReportBuildAttendanceView(APIView):
    permission_classes = [rbac_permission("nomina.attendance.build")]

    def post(self, request, report_id: int):
        company: OrgUnit = request.company
        report = get_object_or_404(FieldCaptureReport, id=report_id, company=company)
        try:
            reports = build_attendance_report(request=request, actor=request.user, report=report)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"count": len(reports), "results": AttendanceReportOut(reports, many=True).data})
