from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.kernels.nomina.models import AttendanceReport, AttendanceSource, AttendanceStatus
from apps.modulos.audit.writer import write_event
from apps.modulos.iam.approvals import approve, mark_executed, request_approval
from apps.modulos.iam.models import ApprovalRequest, OrgUnit
from apps.modulos.hr.models import Employee

from .models_field import Crew, CrewMembership, FieldCaptureReport, FieldCaptureWorkDay, FieldCaptureEvent


@dataclass
class AttendanceAccumulator:
    employee: Employee | None = None
    cedula: str = ""
    employee_name: str = ""
    days_worked: Decimal = Decimal("0.00")
    days_absent: Decimal = Decimal("0.00")
    days_sick: Decimal = Decimal("0.00")
    days_subsidy: Decimal = Decimal("0.00")
    days_accident: Decimal = Decimal("0.00")
    days_transferred: Decimal = Decimal("0.00")
    days_vacation: Decimal = Decimal("0.00")
    overtime_hours: Decimal = Decimal("0.00")
    sunday_worked_days: int = 0
    notes: list[str] = field(default_factory=list)


def _employee_name(employee: Employee | None, fallback: str = "") -> str:
    if employee is None:
        return fallback
    return " ".join(part for part in (employee.first_name, employee.last_name) if part).strip()


def _assert_branch_scope(*, company: OrgUnit, branch: OrgUnit) -> None:
    if branch.parent_id != company.id:
        raise ValueError("La sucursal no pertenece a la empresa activa.")


def _assert_employee_scope(*, company: OrgUnit, employee: Employee | None) -> None:
    if employee is not None and employee.company_id != company.id:
        raise ValueError("El empleado no pertenece a la empresa activa.")


def _write_nomina_event(
    *,
    request,
    actor,
    event_type: str,
    subject_type: str,
    subject_id: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    write_event(
        request=request,
        module="NOMINA",
        event_type=event_type,
        reason_code="NOMINA_OK",
        actor_user=actor,
        subject_type=subject_type,
        subject_id=subject_id,
        metadata=metadata or {},
    )


@transaction.atomic
def create_crew(
    *,
    request,
    actor,
    company: OrgUnit,
    branch: OrgUnit,
    name: str,
    code: str = "",
    foreman: Employee | None = None,
) -> Crew:
    _assert_branch_scope(company=company, branch=branch)
    _assert_employee_scope(company=company, employee=foreman)
    crew = Crew(company=company, branch=branch, name=str(name).strip(), code=str(code or "").strip(), foreman=foreman)
    crew.full_clean()
    crew.save()
    _write_nomina_event(
        request=request,
        actor=actor,
        event_type="FIELD_CREW_CREATED",
        subject_type="FIELD_CREW",
        subject_id=str(crew.id),
        metadata={"branch_id": str(branch.id), "crew_id": str(crew.crew_id)},
    )
    return crew


@transaction.atomic
def add_crew_member(*, crew: Crew, employee: Employee, active_from=None) -> CrewMembership:
    _assert_employee_scope(company=crew.company, employee=employee)
    membership, created = CrewMembership.objects.get_or_create(
        crew=crew,
        employee=employee,
        is_active=True,
        defaults={"active_from": active_from or timezone.localdate()},
    )
    if created:
        membership.full_clean()
    return membership


@transaction.atomic
def upsert_work_day(
    *,
    request,
    actor,
    period,
    crew: Crew,
    work_date,
    notes: str = "",
) -> FieldCaptureWorkDay:
    if crew.company_id != period.company_id:
        raise ValueError("La cuadrilla no pertenece a la empresa del período.")
    work_day, created = FieldCaptureWorkDay.objects.get_or_create(
        crew=crew,
        work_date=work_date,
        defaults={
            "company": period.company,
            "branch": crew.branch,
            "period": period,
            "status": FieldCaptureWorkDay.Status.DRAFT,
            "notes": notes or "",
        },
    )
    if created:
        work_day.full_clean()
        _write_nomina_event(
            request=request,
            actor=actor,
            event_type="FIELD_WORK_DAY_UPSERTED",
            subject_type="FIELD_WORK_DAY",
            subject_id=str(work_day.id),
            metadata={"created": True, "crew_id": str(crew.id), "work_date": str(work_date)},
        )
    return work_day


@transaction.atomic
def upsert_crew_report(
    *,
    request,
    actor,
    work_day: FieldCaptureWorkDay,
    observations: str = "",
) -> FieldCaptureReport:
    report, created = FieldCaptureReport.objects.get_or_create(
        work_day=work_day,
        defaults={
            "company": work_day.company,
            "branch": work_day.branch,
            "period": work_day.period,
            "crew": work_day.crew,
            "status": FieldCaptureReport.Status.SUBMITTED,
            "reported_by": actor,
            "submitted_at": timezone.now(),
            "observations": observations or "",
        },
    )
    if created:
        report.full_clean()
    elif report.status == FieldCaptureReport.Status.DRAFT:
        report.status = FieldCaptureReport.Status.SUBMITTED
        report.reported_by = actor
        report.submitted_at = timezone.now()
        report.observations = observations or report.observations
        report.save(update_fields=["status", "reported_by", "submitted_at", "observations", "updated_at"])

    if work_day.status == FieldCaptureWorkDay.Status.DRAFT:
        work_day.status = FieldCaptureWorkDay.Status.SUBMITTED
        work_day.submitted_by = actor
        work_day.submitted_at = report.submitted_at
        work_day.save(update_fields=["status", "submitted_by", "submitted_at", "updated_at"])

    if created:
        _write_nomina_event(
            request=request,
            actor=actor,
            event_type="FIELD_CREW_REPORT_SUBMITTED",
            subject_type="FIELD_CREW_REPORT",
            subject_id=str(report.id),
            metadata={"work_day_id": str(work_day.id), "crew_id": str(work_day.crew_id)},
        )
    return report


def _event_lookup(*, report: FieldCaptureReport, employee: Employee | None, cedula: str, event_type: str) -> dict[str, Any]:
    lookup: dict[str, Any] = {"report": report, "event_type": event_type}
    if employee is not None:
        lookup["employee"] = employee
    else:
        lookup["employee__isnull"] = True
        lookup["cedula"] = cedula
    return lookup


@transaction.atomic
def record_worker_event(
    *,
    request,
    actor,
    report: FieldCaptureReport,
    event_type: str,
    employee: Employee | None = None,
    cedula: str = "",
    employee_name: str = "",
    day_value: Decimal = Decimal("1.00"),
    overtime_hours: Decimal = Decimal("0.00"),
    sunday_worked_days: int = 0,
    to_crew: Crew | None = None,
    notes: str = "",
) -> FieldCaptureEvent:
    if report.status == FieldCaptureReport.Status.APPROVED:
        raise ValueError("No se pueden registrar eventos en un reporte aprobado.")
    _assert_employee_scope(company=report.company, employee=employee)
    cedula = str(cedula or "").strip()
    employee_name = _employee_name(employee, employee_name)
    if employee is None and not cedula:
        raise ValueError("cedula es requerida para trabajador eventual sin registro HR.")

    existing = FieldCaptureEvent.objects.filter(
        **_event_lookup(report=report, employee=employee, cedula=cedula, event_type=event_type)
    ).first()
    if existing is not None:
        return existing

    event = FieldCaptureEvent(
        company=report.company,
        branch=report.branch,
        period=report.period,
        work_day=report.work_day,
        report=report,
        crew=report.crew,
        employee=employee,
        cedula=cedula,
        employee_name=employee_name,
        event_type=event_type,
        day_value=day_value,
        overtime_hours=overtime_hours,
        sunday_worked_days=int(sunday_worked_days or 0),
        from_crew=report.crew if event_type == FieldCaptureEvent.EventType.TRANSFER else None,
        to_crew=to_crew,
        notes=notes or "",
        recorded_by=actor,
    )
    event.full_clean()
    event.save()

    if event.event_type == FieldCaptureEvent.EventType.TRANSFER and employee is not None and to_crew is not None:
        CrewMembership.objects.filter(crew=report.crew, employee=employee, is_active=True).update(
            is_active=False,
            active_to=report.work_day.work_date,
            updated_at=timezone.now(),
        )
        CrewMembership.objects.get_or_create(
            crew=to_crew,
            employee=employee,
            is_active=True,
            defaults={"active_from": report.work_day.work_date},
        )

    audit_event = (
        "FIELD_WORKER_TRANSFER_RECORDED"
        if event.event_type == FieldCaptureEvent.EventType.TRANSFER
        else "FIELD_WORKER_EVENT_RECORDED"
    )
    _write_nomina_event(
        request=request,
        actor=actor,
        event_type=audit_event,
        subject_type="FIELD_WORKER_EVENT",
        subject_id=str(event.id),
        metadata={"report_id": str(report.id), "event_type": event.event_type},
    )
    return event


@transaction.atomic
def request_report_approval(*, request, actor, report: FieldCaptureReport, reason: str = "") -> ApprovalRequest:
    report = FieldCaptureReport.objects.select_for_update().get(pk=report.pk)
    if report.status == FieldCaptureReport.Status.APPROVED:
        raise ValueError("El reporte ya está aprobado.")
    approval = request_approval(
        request=request,
        company=report.company,
        branch=report.branch,
        requested_by=actor,
        action_type="NOMINA_FIELD_REPORT_APPROVAL",
        required_permission="nomina.attendance.approve",
        subject_type="FIELD_CREW_REPORT",
        subject_id=str(report.id),
        reason=reason or "",
        payload={"report_id": report.id, "work_day_id": report.work_day_id, "crew_id": report.crew_id},
        idempotency_key=f"field-report-approval:{report.id}",
    )
    report.approval_request = approval
    report.status = FieldCaptureReport.Status.APPROVAL_PENDING
    report.work_day.status = FieldCaptureWorkDay.Status.APPROVAL_PENDING
    report.save(update_fields=["approval_request", "status", "updated_at"])
    report.work_day.save(update_fields=["status", "updated_at"])
    return approval


@transaction.atomic
def approve_report(*, request, approver, report: FieldCaptureReport, approval: ApprovalRequest, note: str = "") -> FieldCaptureReport:
    report = FieldCaptureReport.objects.select_for_update().get(pk=report.pk)
    approved = approve(approval=approval, approver=approver, note=note, request=request)
    before_status = report.status
    report.status = FieldCaptureReport.Status.APPROVED
    report.approved_by = approver
    report.approved_at = timezone.now()
    report.approval_request = approved
    report.save(update_fields=["status", "approved_by", "approved_at", "approval_request", "updated_at"])
    report.work_day.status = FieldCaptureWorkDay.Status.APPROVED
    report.work_day.save(update_fields=["status", "updated_at"])
    mark_executed(approval=approved, actor=approver, request=request)
    _write_nomina_event(
        request=request,
        actor=approver,
        event_type="FIELD_CREW_REPORT_APPROVED",
        subject_type="FIELD_CREW_REPORT",
        subject_id=str(report.id),
        metadata={"before_status": before_status, "approval_request_id": str(approved.request_id)},
    )
    return report


def _accumulator_key(event: FieldCaptureEvent) -> tuple[str, str]:
    if event.employee_id:
        return ("employee", str(event.employee_id))
    return ("cedula", event.cedula)


def _apply_event(acc: AttendanceAccumulator, event: FieldCaptureEvent) -> None:
    value = Decimal(str(event.day_value or Decimal("0.00")))
    if event.event_type == FieldCaptureEvent.EventType.PRESENT:
        acc.days_worked += value
    elif event.event_type == FieldCaptureEvent.EventType.ABSENT:
        acc.days_absent += value
    elif event.event_type == FieldCaptureEvent.EventType.SICK:
        acc.days_sick += value
    elif event.event_type == FieldCaptureEvent.EventType.SUBSIDY:
        acc.days_subsidy += value
    elif event.event_type == FieldCaptureEvent.EventType.ACCIDENT:
        acc.days_accident += value
    elif event.event_type == FieldCaptureEvent.EventType.TRANSFER:
        acc.days_transferred += value
    elif event.event_type == FieldCaptureEvent.EventType.VACATION:
        acc.days_vacation += value
    acc.overtime_hours += Decimal(str(event.overtime_hours or Decimal("0.00")))
    acc.sunday_worked_days += int(event.sunday_worked_days or 0)
    if event.notes:
        acc.notes.append(event.notes)


@transaction.atomic
def build_attendance_report(*, request, actor, report: FieldCaptureReport) -> list[AttendanceReport]:
    report = FieldCaptureReport.objects.select_for_update().get(pk=report.pk)
    if report.status != FieldCaptureReport.Status.APPROVED:
        raise ValueError("Solo se puede agregar asistencia desde reportes de campo aprobados.")

    grouped: dict[tuple[str, str], AttendanceAccumulator] = defaultdict(AttendanceAccumulator)
    for event in report.worker_events.select_related("employee").order_by("id"):
        key = _accumulator_key(event)
        acc = grouped[key]
        acc.employee = event.employee
        acc.cedula = event.cedula
        acc.employee_name = _employee_name(event.employee, event.employee_name)
        _apply_event(acc, event)

    created_reports: list[AttendanceReport] = []
    for acc in grouped.values():
        lookup = {
            "company": report.company,
            "branch": report.branch,
            "period": report.period,
            "source": AttendanceSource.SUPERVISOR_APP,
        }
        if acc.employee is not None:
            lookup["employee"] = acc.employee
        else:
            lookup["employee__isnull"] = True
            lookup["cedula"] = acc.cedula

        attendance = AttendanceReport.objects.filter(**lookup).first()
        if attendance is None:
            attendance = AttendanceReport(
                company=report.company,
                branch=report.branch,
                period=report.period,
                employee=acc.employee,
                source=AttendanceSource.SUPERVISOR_APP,
            )

        attendance.status = AttendanceStatus.APPROVED
        attendance.employee_name = acc.employee_name
        attendance.cedula = acc.cedula
        attendance.days_worked = acc.days_worked
        attendance.days_absent = acc.days_absent
        attendance.days_sick = acc.days_sick
        attendance.days_subsidy = acc.days_subsidy
        attendance.days_accident = acc.days_accident
        attendance.days_transferred = acc.days_transferred
        attendance.days_vacation = acc.days_vacation
        attendance.overtime_hours = acc.overtime_hours
        attendance.sunday_worked_days = acc.sunday_worked_days
        attendance.observations = report.observations
        attendance.approved_by = report.approved_by
        attendance.approved_at = report.approved_at
        attendance.submitted_by = report.reported_by
        attendance.submitted_at = report.submitted_at
        if acc.notes:
            attendance.observations = "\n".join([attendance.observations, *acc.notes]).strip()
        attendance.full_clean()
        attendance.save()
        created_reports.append(attendance)

    _write_nomina_event(
        request=request,
        actor=actor,
        event_type="ATTENDANCE_REPORT_BUILT",
        subject_type="FIELD_CREW_REPORT",
        subject_id=str(report.id),
        metadata={"attendance_reports": [str(row.id) for row in created_reports]},
    )
    return created_reports
