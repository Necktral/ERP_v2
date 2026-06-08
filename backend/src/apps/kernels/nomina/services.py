from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date as _date
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.modulos.audit.writer import write_event
from apps.modulos.iam.models import OrgUnit

from .models import (
    AttendanceReport,
    AttendanceSource,
    AttendanceStatus,
    DEFAULT_INSS_LABORAL,
    DEFAULT_INSS_PATRONAL_LARGE,
    DEFAULT_INSS_PATRONAL_SMALL,
    DEFAULT_INSS_SIZE_THRESHOLD,
    DEFAULT_INATEC,
    DEFAULT_OVERTIME_RATE,
    DEFAULT_SUBSIDY_EMPLOYER_DAYS,
    DEFAULT_SUBSIDY_INSS_RATE,
    DEFAULT_SUNDAY_RATE,
    DEFAULT_THIRTEENTH_RATE,
    DEFAULT_VACATION_RATE,
    DEFAULT_MIN_WAGE_AGRO,
    FieldAttendanceConsolidation,
    FieldAttendanceConsolidationStatus,
    FieldCrew,
    FieldCrewReport,
    FieldCrewReportLine,
    FieldCrewReportStatus,
    FieldRollCall,
    FieldRollCallLine,
    FieldRollCallLineStatus,
    FieldTransfer,
    FieldWorkDay,
    FieldWorkDayStatus,
    FieldWorkerEvent,
    FieldWorkerEventType,
    Holiday,
    IRBracket,
    NominaConfig,
    PayrollEntry,
    PayrollPeriod,
    PayrollSheet,
)


# ---------------------------------------------------------------------------
# NominaConfig — crear / actualizar configuración
# ---------------------------------------------------------------------------

NICARAGUA_2026_IR_BRACKETS = [
    # (order, min, max,    base_tax, rate)
    (1,      0,     100_000,  0,       Decimal("0.00")),
    (2, 100_000,    200_000,  0,       Decimal("0.15")),
    (3, 200_000,    350_000,  15_000,  Decimal("0.20")),
    (4, 350_000,    500_000,  45_000,  Decimal("0.25")),
    (5, 500_000,    None,     82_500,  Decimal("0.30")),
]


def create_default_nicaragua_config(
    *,
    request,
    actor,
    company: OrgUnit,
    fiscal_year: int | None = None,
    effective_from=None,
) -> NominaConfig:
    """
    Crea una NominaConfig con los valores por defecto de Nicaragua 2026
    y la tabla IR 2026. Idempotente: si ya existe para ese año, la retorna.
    """
    year = fiscal_year or timezone.localdate().year
    ref_date = effective_from or timezone.localdate().replace(month=1, day=1)

    with transaction.atomic():
        existing = NominaConfig.objects.filter(
            company=company, fiscal_year=year, effective_from=ref_date
        ).first()
        if existing:
            return existing

        cfg = NominaConfig.objects.create(
            company=company,
            fiscal_year=year,
            effective_from=ref_date,
            is_active=True,
            inss_laboral_rate=DEFAULT_INSS_LABORAL,
            inss_patronal_rate_small=DEFAULT_INSS_PATRONAL_SMALL,
            inss_patronal_rate_large=DEFAULT_INSS_PATRONAL_LARGE,
            inss_size_threshold=DEFAULT_INSS_SIZE_THRESHOLD,
            inatec_rate=DEFAULT_INATEC,
            vacation_rate=DEFAULT_VACATION_RATE,
            thirteenth_month_rate=DEFAULT_THIRTEENTH_RATE,
            overtime_rate=DEFAULT_OVERTIME_RATE,
            sunday_bonus_rate=DEFAULT_SUNDAY_RATE,
            subsidy_employer_days=DEFAULT_SUBSIDY_EMPLOYER_DAYS,
            subsidy_inss_rate=DEFAULT_SUBSIDY_INSS_RATE,
            min_wage_agro=DEFAULT_MIN_WAGE_AGRO,
            created_by=actor,
            notes=f"Config Nicaragua {year} — valores por defecto INSS/IR",
        )

        # Crear tabla IR 2026
        for order, min_inc, max_inc, base_tax, rate in NICARAGUA_2026_IR_BRACKETS:
            IRBracket.objects.create(
                config=cfg,
                order=order,
                min_income=Decimal(str(min_inc)),
                max_income=Decimal(str(max_inc)) if max_inc is not None else None,
                base_tax=Decimal(str(base_tax)),
                rate=rate,
            )

        write_event(
            request=request,
            module="NOMINA",
            event_type="NOMINA_CONFIG_CREATED",
            reason_code="NOMINA_OK",
            actor_user=actor,
            subject_type="NOMINA_CONFIG",
            subject_id=str(cfg.id),
            metadata={
                "fiscal_year": year,
                "company_id": company.id,
                "inss_laboral": str(cfg.inss_laboral_rate),
                "inss_patronal_large": str(cfg.inss_patronal_rate_large),
                "inatec": str(cfg.inatec_rate),
            },
        )

    return cfg


def update_nomina_config(
    *,
    request,
    actor,
    config: NominaConfig,
    data: dict,
) -> NominaConfig:
    """Actualiza campos individuales de una NominaConfig."""
    allowed_fields = {
        "inss_laboral_rate", "inss_patronal_rate_small", "inss_patronal_rate_large",
        "inss_size_threshold", "inatec_rate", "vacation_rate", "thirteenth_month_rate",
        "overtime_rate", "sunday_bonus_rate", "seventh_day_rate",
        "subsidy_employer_days", "subsidy_inss_rate",
        "min_wage_agro", "min_wage_general",
        "payment_deadline_days", "late_payment_surcharge",
        "is_active", "notes",
    }
    changed = []
    with transaction.atomic():
        for field, value in data.items():
            if field not in allowed_fields:
                continue
            if getattr(config, field) != value:
                setattr(config, field, value)
                changed.append(field)
        if changed:
            config.save(update_fields=changed + ["updated_at"] if "updated_at" not in changed else changed)
            write_event(
                request=request,
                module="NOMINA",
                event_type="NOMINA_CONFIG_UPDATED",
                reason_code="NOMINA_OK",
                actor_user=actor,
                subject_type="NOMINA_CONFIG",
                subject_id=str(config.id),
                metadata={"changed_fields": changed},
            )
    return config


def upsert_ir_brackets(
    *,
    request,
    actor,
    config: NominaConfig,
    brackets: list[dict],
) -> list[IRBracket]:
    """
    Reemplaza la tabla IR de una config con los tramos dados.
    Cada dict: {order, min_income, max_income (nullable), base_tax, rate}
    """
    with transaction.atomic():
        IRBracket.objects.filter(config=config).delete()
        created = []
        for b in brackets:
            created.append(IRBracket.objects.create(
                config=config,
                order=int(b["order"]),
                min_income=Decimal(str(b["min_income"])),
                max_income=Decimal(str(b["max_income"])) if b.get("max_income") is not None else None,
                base_tax=Decimal(str(b.get("base_tax", "0"))),
                rate=Decimal(str(b["rate"])),
            ))
        write_event(
            request=request,
            module="NOMINA",
            event_type="NOMINA_IR_TABLE_UPDATED",
            reason_code="NOMINA_OK",
            actor_user=actor,
            subject_type="NOMINA_CONFIG",
            subject_id=str(config.id),
            metadata={"brackets_count": len(created)},
        )
    return created


# ---------------------------------------------------------------------------
# PayrollPeriod
# ---------------------------------------------------------------------------

def create_period(
    *,
    request,
    actor,
    company: OrgUnit,
    year: int,
    month: int,
    period_type: str,
    start_date,
    end_date,
    working_days: int = 15,
    exchange_rate_usd: Decimal | None = None,
    notes: str = "",
) -> PayrollPeriod:
    from .models import PeriodStatus

    _ = NominaConfig.get_active(company=company, date=start_date)
    rate = exchange_rate_usd or Decimal("36.6243")

    with transaction.atomic():
        period = PayrollPeriod.objects.create(
            company=company,
            year=year,
            month=month,
            period_type=period_type,
            start_date=start_date,
            end_date=end_date,
            working_days=working_days,
            exchange_rate_usd=rate,
            status=PeriodStatus.DRAFT,
            notes=notes or "",
            created_by=actor,
        )
        write_event(
            request=request,
            module="NOMINA",
            event_type="NOMINA_PERIOD_CREATED",
            reason_code="NOMINA_OK",
            actor_user=actor,
            subject_type="PAYROLL_PERIOD",
            subject_id=str(period.id),
            metadata={
                "year": year, "month": month,
                "period_type": period_type,
                "exchange_rate_usd": str(rate),
            },
        )
    return period


# ---------------------------------------------------------------------------
# PayrollSheet
# ---------------------------------------------------------------------------

def create_sheet(
    *,
    request,
    actor,
    period: PayrollPeriod,
    sheet_name: str,
    has_inss: bool = True,
    branch: OrgUnit | None = None,
    notes: str = "",
) -> PayrollSheet:
    from .models import SheetStatus
    with transaction.atomic():
        sheet = PayrollSheet.objects.create(
            period=period,
            branch=branch,
            sheet_name=sheet_name,
            has_inss=has_inss,
            status=SheetStatus.DRAFT,
            notes=notes or "",
        )
        write_event(
            request=request,
            module="NOMINA",
            event_type="NOMINA_SHEET_CREATED",
            reason_code="NOMINA_OK",
            actor_user=actor,
            subject_type="PAYROLL_SHEET",
            subject_id=str(sheet.id),
            metadata={
                "period_id": period.id,
                "sheet_name": sheet_name,
                "has_inss": has_inss,
            },
        )
    return sheet


def submit_sheet(*, request, actor, sheet: PayrollSheet) -> PayrollSheet:
    """El jefe de área envía la planilla al encargado de nómina."""
    from .models import SheetStatus
    if sheet.status != SheetStatus.DRAFT:
        raise ValueError(f"Solo se puede enviar desde DRAFT, estado actual: {sheet.status}")
    with transaction.atomic():
        sheet.status = SheetStatus.SUBMITTED
        sheet.submitted_by = actor
        sheet.submitted_at = timezone.now()
        sheet.save(update_fields=["status", "submitted_by", "submitted_at"])
        write_event(
            request=request,
            module="NOMINA",
            event_type="NOMINA_SHEET_SUBMITTED",
            reason_code="NOMINA_OK",
            actor_user=actor,
            subject_type="PAYROLL_SHEET",
            subject_id=str(sheet.id),
            metadata={"period_id": sheet.period_id},
        )
    return sheet


def approve_sheet(*, request, actor, sheet: PayrollSheet) -> PayrollSheet:
    """El encargado de nómina aprueba la planilla."""
    from .models import SheetStatus
    if sheet.status not in (SheetStatus.SUBMITTED, SheetStatus.REVIEWED):
        raise ValueError(f"No se puede aprobar desde estado: {sheet.status}")
    with transaction.atomic():
        sheet.status = SheetStatus.APPROVED
        sheet.approved_by = actor
        sheet.approved_at = timezone.now()
        sheet.save(update_fields=["status", "approved_by", "approved_at"])
        write_event(
            request=request,
            module="NOMINA",
            event_type="NOMINA_SHEET_APPROVED",
            reason_code="NOMINA_OK",
            actor_user=actor,
            subject_type="PAYROLL_SHEET",
            subject_id=str(sheet.id),
            metadata={"period_id": sheet.period_id},
        )
    return sheet


# ---------------------------------------------------------------------------
# PayrollEntry — calcular y guardar
# ---------------------------------------------------------------------------

def compute_entry(*, entry: PayrollEntry, worker_count: int = 999) -> PayrollEntry:
    """
    Aplica compute_all() usando la NominaConfig activa de la empresa.
    """
    company = entry.sheet.period.company
    period_date = entry.sheet.period.start_date
    config = NominaConfig.get_active(company=company, date=period_date)
    entry.compute_all(config=config, worker_count=worker_count)
    entry.save()
    return entry


def compute_all_entries_in_sheet(*, sheet: PayrollSheet, worker_count: int = 999) -> int:
    """Recalcula todas las entradas de una planilla. Retorna cantidad procesada."""
    company = sheet.period.company
    period_date = sheet.period.start_date
    config = NominaConfig.get_active(company=company, date=period_date)
    count = 0
    for entry in sheet.entries.all():
        entry.compute_all(config=config, worker_count=worker_count)
        entry.save()
        count += 1
    return count


# ---------------------------------------------------------------------------
# Field Attendance — foundation backend only
# ---------------------------------------------------------------------------

class FieldAttendanceError(ValueError):
    """Error de dominio para reglas de asistencia de campo."""

    def __init__(self, code: str, message: str, *, context: dict | None = None):
        self.code = code
        self.context = context or {}
        super().__init__(message)


FIELD_EVENTS_REQUIRING_DETAILS = {
    FieldWorkerEventType.SICK,
    FieldWorkerEventType.ACCIDENT,
    FieldWorkerEventType.OTHER,
}

FIELD_PRESENT_EVENTS = {
    FieldWorkerEventType.PRESENT,
    FieldWorkerEventType.LEFT_EARLY,
    FieldWorkerEventType.JOINED_LATE,
}

FIELD_PRIMARY_EVENT_PRIORITY = [
    FieldWorkerEventType.ACCIDENT,
    FieldWorkerEventType.SICK,
    FieldWorkerEventType.PERMISSION,
    FieldWorkerEventType.DISMISSED,
    FieldWorkerEventType.ABSENT,
    FieldWorkerEventType.LEFT_EARLY,
    FieldWorkerEventType.JOINED_LATE,
    FieldWorkerEventType.PRESENT,
    FieldWorkerEventType.TRANSFERRED,
    FieldWorkerEventType.OTHER,
]


def _field_error(code: str, message: str, *, context: dict | None = None) -> FieldAttendanceError:
    return FieldAttendanceError(code, message, context=context)


def _validate_branch_scope(*, company: OrgUnit, branch: OrgUnit | None) -> None:
    if branch is None:
        return
    if branch.unit_type != OrgUnit.UnitType.BRANCH or branch.parent_id != company.id:
        raise _field_error(
            "invalid_scope",
            "La sucursal/finca no pertenece a la empresa indicada.",
            context={"company_id": company.id, "branch_id": branch.id},
        )


def _validate_period_scope(*, company: OrgUnit, payroll_period: PayrollPeriod | None, work_date) -> None:
    if payroll_period is None:
        return
    if payroll_period.company_id != company.id:
        raise _field_error(
            "invalid_scope",
            "El periodo de nomina no pertenece a la empresa indicada.",
            context={"company_id": company.id, "period_id": payroll_period.id},
        )
    if not (payroll_period.start_date <= work_date <= payroll_period.end_date):
        raise _field_error(
            "invalid_period_date",
            "La fecha de campo no cae dentro del periodo de nomina.",
            context={
                "work_date": str(work_date),
                "start_date": str(payroll_period.start_date),
                "end_date": str(payroll_period.end_date),
            },
        )


def _validate_work_day_mutable(work_day: FieldWorkDay) -> None:
    if work_day.status in {FieldWorkDayStatus.APPROVED, FieldWorkDayStatus.LOCKED}:
        raise _field_error(
            "invalid_state",
            "El dia de campo aprobado o bloqueado no admite cambios directos.",
            context={"work_day_id": work_day.id, "status": work_day.status},
        )


def _validate_employee_scope(*, company: OrgUnit, employee, field_name: str = "employee") -> None:
    if not employee or not getattr(employee, "pk", None):
        raise _field_error("missing_employee", f"{field_name} es requerido.")
    if employee.company_id != company.id:
        raise _field_error(
            "employee_out_of_scope",
            "El empleado no pertenece a la empresa del dia de campo.",
            context={"company_id": company.id, "employee_id": employee.id},
        )
    if not employee.is_active:
        raise _field_error(
            "inactive_employee",
            "El empleado debe estar activo para asistencia de campo.",
            context={"employee_id": employee.id},
        )


def _validate_unique_employees(lines: list[dict]) -> None:
    seen: set[int] = set()
    for line in lines:
        employee = line.get("employee")
        employee_id = getattr(employee, "id", None)
        if employee_id is None:
            raise _field_error("missing_employee", "employee es requerido.")
        if employee_id in seen:
            raise _field_error(
                "duplicate_employee",
                "El mismo empleado aparece mas de una vez en el payload.",
                context={"employee_id": employee_id},
            )
        seen.add(employee_id)


def _coerce_rollcall_status(value: str | None) -> str:
    status = value or FieldRollCallLineStatus.UNKNOWN
    if status not in FieldRollCallLineStatus.values:
        raise _field_error("invalid_rollcall_status", "Estado de lista inicial invalido.", context={"status": status})
    return status


def _coerce_event_type(value: str | None) -> str:
    event_type = value or FieldWorkerEventType.PRESENT
    if event_type not in FieldWorkerEventType.values:
        raise _field_error("invalid_event_type", "Tipo de evento de campo invalido.", context={"event_type": event_type})
    return event_type


def _coerce_day_value(value, *, event_type: str) -> Decimal:
    if value is None:
        if event_type in {FieldWorkerEventType.PRESENT, FieldWorkerEventType.LEFT_EARLY, FieldWorkerEventType.JOINED_LATE}:
            return Decimal("1.00")
        return Decimal("0.00")
    day_value = Decimal(str(value))
    if day_value < Decimal("0.00") or day_value > Decimal("1.00"):
        raise _field_error("invalid_day_value", "day_value debe estar entre 0.00 y 1.00.")
    return day_value.quantize(Decimal("0.01"))


def _require_details_if_needed(*, event_type: str, details: str) -> None:
    if event_type in FIELD_EVENTS_REQUIRING_DETAILS and not (details or "").strip():
        raise _field_error(
            "missing_required_detail",
            "El evento de campo requiere detalle obligatorio.",
            context={"event_type": event_type},
        )


def _employee_label(employee) -> str:
    return f"{employee.first_name} {employee.last_name}".strip() or employee.employee_code or str(employee.id)


def _audit(
    *,
    request,
    actor,
    event_type: str,
    subject_type: str,
    subject_id,
    metadata: dict | None = None,
    reason_code: str = "FIELD_ATTENDANCE_OK",
) -> None:
    write_event(
        request=request,
        module="NOMINA",
        event_type=event_type,
        reason_code=reason_code,
        actor_user=actor,
        subject_type=subject_type,
        subject_id=str(subject_id),
        metadata=metadata or {},
    )


def open_field_work_day(
    *,
    request,
    actor,
    company: OrgUnit,
    work_date,
    branch: OrgUnit | None = None,
    payroll_period: PayrollPeriod | None = None,
    notes: str = "",
) -> FieldWorkDay:
    """Abre un dia operativo de campo para lista, cuadrillas y consolidacion."""
    _validate_branch_scope(company=company, branch=branch)
    _validate_period_scope(company=company, payroll_period=payroll_period, work_date=work_date)
    lookup = {"company": company, "work_date": work_date}
    if branch is None:
        lookup["branch__isnull"] = True
    else:
        lookup["branch"] = branch
    if FieldWorkDay.objects.filter(**lookup).exists():
        raise _field_error("duplicate_work_day", "Ya existe un dia de campo para ese scope y fecha.")

    with transaction.atomic():
        work_day = FieldWorkDay.objects.create(
            company=company,
            branch=branch,
            payroll_period=payroll_period,
            work_date=work_date,
            status=FieldWorkDayStatus.OPEN,
            opened_by=actor,
            notes=notes or "",
        )
        _audit(
            request=request,
            actor=actor,
            event_type="FIELD_WORK_DAY_OPENED",
            subject_type="FIELD_WORK_DAY",
            subject_id=work_day.id,
            metadata={
                "company_id": company.id,
                "branch_id": branch.id if branch else None,
                "payroll_period_id": payroll_period.id if payroll_period else None,
                "work_date": str(work_date),
            },
        )
    return work_day


def submit_rollcall(
    *,
    request,
    actor,
    work_day: FieldWorkDay,
    lines: list[dict],
    notes: str = "",
) -> FieldRollCall:
    """Registra la lista inicial del mandador para un dia de campo."""
    _validate_work_day_mutable(work_day)
    if FieldRollCall.objects.filter(work_day=work_day).exists():
        raise _field_error("invalid_state", "La lista inicial ya fue enviada para este dia.")
    if not lines:
        raise _field_error("empty_rollcall", "La lista inicial requiere al menos un empleado.")
    _validate_unique_employees(lines)

    with transaction.atomic():
        rollcall = FieldRollCall.objects.create(work_day=work_day, submitted_by=actor, notes=notes or "")
        created_lines = []
        for line in lines:
            employee = line.get("employee")
            _validate_employee_scope(company=work_day.company, employee=employee)
            status = _coerce_rollcall_status(line.get("status"))
            created_lines.append(FieldRollCallLine(
                rollcall=rollcall,
                employee=employee,
                status=status,
                absence_reason=line.get("absence_reason", "") or "",
                note=line.get("note", "") or "",
            ))
        FieldRollCallLine.objects.bulk_create(created_lines)
        work_day.status = (
            FieldWorkDayStatus.CREW_REPORTS_PENDING
            if work_day.crews.exists()
            else FieldWorkDayStatus.ROLLCALL_SUBMITTED
        )
        work_day.save(update_fields=["status", "updated_at"])
        _audit(
            request=request,
            actor=actor,
            event_type="FIELD_ROLLCALL_SUBMITTED",
            subject_type="FIELD_ROLLCALL",
            subject_id=rollcall.id,
            metadata={"work_day_id": work_day.id, "line_count": len(created_lines)},
        )
    return rollcall


def create_field_crew(
    *,
    request,
    actor,
    work_day: FieldWorkDay,
    name: str,
    supervisor_employee,
) -> FieldCrew:
    """Crea una cuadrilla del dia con capataz/responsable HR."""
    _validate_work_day_mutable(work_day)
    if not (name or "").strip():
        raise _field_error("missing_crew_name", "El nombre de la cuadrilla es requerido.")
    _validate_employee_scope(company=work_day.company, employee=supervisor_employee, field_name="supervisor_employee")

    with transaction.atomic():
        crew = FieldCrew.objects.create(
            work_day=work_day,
            name=name.strip(),
            supervisor_employee=supervisor_employee,
        )
        if work_day.status in {FieldWorkDayStatus.OPEN, FieldWorkDayStatus.ROLLCALL_SUBMITTED}:
            work_day.status = FieldWorkDayStatus.CREW_REPORTS_PENDING
            work_day.save(update_fields=["status", "updated_at"])
        _audit(
            request=request,
            actor=actor,
            event_type="FIELD_CREW_CREATED",
            subject_type="FIELD_CREW",
            subject_id=crew.id,
            metadata={
                "work_day_id": work_day.id,
                "supervisor_employee_id": supervisor_employee.id,
                "crew_name": crew.name,
            },
        )
    return crew


def submit_crew_report(
    *,
    request,
    actor,
    crew: FieldCrew,
    lines: list[dict],
    labor_code: str = "",
    labor_name: str = "",
    zone_label: str = "",
    notes: str = "",
) -> FieldCrewReport:
    """Envio del reporte diario de cuadrilla por capataz."""
    work_day = crew.work_day
    _validate_work_day_mutable(work_day)
    if not lines:
        raise _field_error("empty_crew_report", "El reporte de cuadrilla requiere al menos un empleado.")
    _validate_unique_employees(lines)

    with transaction.atomic():
        report, created = FieldCrewReport.objects.get_or_create(crew=crew)
        if not created and report.status not in {
            FieldCrewReportStatus.DRAFT,
            FieldCrewReportStatus.RETURNED_FOR_CORRECTION,
        }:
            raise _field_error(
                "invalid_state",
                "El reporte de cuadrilla no puede reenviarse desde su estado actual.",
                context={"report_id": report.id, "status": report.status},
            )
        if not created:
            report.lines.all().delete()
        created_lines = []
        for line in lines:
            employee = line.get("employee")
            _validate_employee_scope(company=work_day.company, employee=employee)
            event_type = _coerce_event_type(line.get("event_type"))
            details = line.get("notes", "") or ""
            _require_details_if_needed(event_type=event_type, details=details)
            created_lines.append(FieldCrewReportLine(
                report=report,
                employee=employee,
                event_type=event_type,
                day_value=_coerce_day_value(line.get("day_value"), event_type=event_type),
                notes=details,
            ))
        report.status = FieldCrewReportStatus.SUBMITTED
        report.labor_code = labor_code or ""
        report.labor_name = labor_name or ""
        report.zone_label = zone_label or ""
        report.submitted_by = actor
        report.submitted_at = timezone.now()
        report.notes = notes or ""
        report.save(update_fields=[
            "status", "labor_code", "labor_name", "zone_label",
            "submitted_by", "submitted_at", "notes", "updated_at",
        ])
        FieldCrewReportLine.objects.bulk_create(created_lines)
        if work_day.status != FieldWorkDayStatus.IN_REVIEW:
            work_day.status = FieldWorkDayStatus.IN_REVIEW
            work_day.save(update_fields=["status", "updated_at"])
        _audit(
            request=request,
            actor=actor,
            event_type="FIELD_CREW_REPORT_SUBMITTED",
            subject_type="FIELD_CREW_REPORT",
            subject_id=report.id,
            metadata={
                "work_day_id": work_day.id,
                "crew_id": crew.id,
                "line_count": len(created_lines),
                "labor_code": report.labor_code,
            },
        )
    return report


def record_worker_event(
    *,
    request,
    actor,
    work_day: FieldWorkDay,
    employee,
    event_type: str,
    details: str = "",
    crew_report: FieldCrewReport | None = None,
    occurred_at=None,
    metadata: dict | None = None,
) -> FieldWorkerEvent:
    """Registra una novedad individual auditable del trabajador."""
    _validate_work_day_mutable(work_day)
    _validate_employee_scope(company=work_day.company, employee=employee)
    normalized_event_type = _coerce_event_type(event_type)
    _require_details_if_needed(event_type=normalized_event_type, details=details)
    if crew_report is not None and crew_report.crew.work_day_id != work_day.id:
        raise _field_error(
            "invalid_scope",
            "El reporte de cuadrilla no pertenece al dia de campo.",
            context={"work_day_id": work_day.id, "crew_report_id": crew_report.id},
        )

    with transaction.atomic():
        event = FieldWorkerEvent.objects.create(
            work_day=work_day,
            crew_report=crew_report,
            employee=employee,
            event_type=normalized_event_type,
            occurred_at=occurred_at or timezone.now(),
            details=details or "",
            metadata=metadata or {},
            created_by=actor,
        )
        _audit(
            request=request,
            actor=actor,
            event_type="FIELD_WORKER_EVENT_RECORDED",
            subject_type="FIELD_WORKER_EVENT",
            subject_id=event.id,
            metadata={
                "work_day_id": work_day.id,
                "employee_id": employee.id,
                "employee": _employee_label(employee),
                "event_type": normalized_event_type,
                "crew_report_id": crew_report.id if crew_report else None,
            },
        )
    return event


def transfer_worker(
    *,
    request,
    actor,
    work_day: FieldWorkDay,
    employee,
    from_crew: FieldCrew,
    to_crew: FieldCrew,
    reason: str,
    transferred_at=None,
) -> FieldTransfer:
    """Traslada un trabajador entre cuadrillas sin duplicar asistencia."""
    _validate_work_day_mutable(work_day)
    _validate_employee_scope(company=work_day.company, employee=employee)
    if from_crew.id == to_crew.id:
        raise _field_error("invalid_transfer", "La cuadrilla origen y destino deben ser distintas.")
    if from_crew.work_day_id != work_day.id or to_crew.work_day_id != work_day.id:
        raise _field_error("invalid_scope", "Ambas cuadrillas deben pertenecer al mismo dia de campo.")
    if not (reason or "").strip():
        raise _field_error("missing_required_detail", "El traslado requiere motivo.")

    with transaction.atomic():
        transfer = FieldTransfer.objects.create(
            work_day=work_day,
            employee=employee,
            from_crew=from_crew,
            to_crew=to_crew,
            reason=reason.strip(),
            transferred_at=transferred_at or timezone.now(),
            created_by=actor,
        )
        FieldWorkerEvent.objects.create(
            work_day=work_day,
            employee=employee,
            event_type=FieldWorkerEventType.TRANSFERRED,
            occurred_at=transfer.transferred_at,
            details=transfer.reason,
            metadata={"from_crew_id": from_crew.id, "to_crew_id": to_crew.id},
            created_by=actor,
        )
        _audit(
            request=request,
            actor=actor,
            event_type="FIELD_WORKER_TRANSFERRED",
            subject_type="FIELD_TRANSFER",
            subject_id=transfer.id,
            metadata={
                "work_day_id": work_day.id,
                "employee_id": employee.id,
                "from_crew_id": from_crew.id,
                "to_crew_id": to_crew.id,
            },
        )
    return transfer


def _has_transfer_between(crews: set[int], transfers: list[FieldTransfer]) -> bool:
    for transfer in transfers:
        pair = {transfer.from_crew_id, transfer.to_crew_id}
        if pair.issubset(crews):
            return True
    return False


def _primary_event(event_types: set[str], *, rollcall_status: str | None) -> str:
    if not event_types and rollcall_status == FieldRollCallLineStatus.PRESENT:
        return FieldWorkerEventType.PRESENT
    if not event_types and rollcall_status == FieldRollCallLineStatus.ABSENT:
        return FieldWorkerEventType.ABSENT
    for event_type in FIELD_PRIMARY_EVENT_PRIORITY:
        if event_type in event_types:
            return event_type
    return ""


def _calculate_day_value(
    *,
    primary_event_type: str,
    rollcall_status: str | None,
    crew_lines: list[FieldCrewReportLine],
    is_split_transfer: bool = False,
) -> Decimal:
    if crew_lines:
        if is_split_transfer:
            # Día partido por traslado entre cuadrillas: SUMA las porciones (tope 1.0),
            # para no sub-pagar al que trabajó en dos cuadrillas el mismo día.
            total = sum((line.day_value for line in crew_lines), Decimal("0.00"))
            return min(total, Decimal("1.00")).quantize(Decimal("0.01"))
        # Sin traslado: máximo (anti-doble-pago; un duplicado sin traslado queda BLOCKED aparte).
        return max(line.day_value for line in crew_lines).quantize(Decimal("0.01"))
    if primary_event_type in {FieldWorkerEventType.PRESENT, FieldWorkerEventType.LEFT_EARLY, FieldWorkerEventType.JOINED_LATE}:
        return Decimal("1.00")
    if rollcall_status == FieldRollCallLineStatus.PRESENT:
        return Decimal("1.00")
    return Decimal("0.00")


def resolve_worker_inss(employee, *, period=None) -> bool | None:
    """Resuelve si el trabajador cotiza INSS, para el snapshot de la consolidación.

    Reemplaza el `getattr(employee, "has_inss")` —que SIEMPRE devolvía None porque
    hr.Employee no tiene ese campo— por una resolución real:
      1) F2-1 (afiliación/elección de régimen por período): punto único de cableado cuando aterrice.
      2) Continuidad: la `has_inss` del último PayrollEntry conocido del empleado
         (la última decisión del planillero), para automatizar la búsqueda manual.
      3) None si no hay información (desconocido).
    """
    if employee is None:
        return None
    # (1) F2-1: elección del período > afiliación fechada del empleado.
    if period is not None:
        from .models import EmployeeInssEnrollment, InssRegime, PayrollInssElection

        elected = (
            PayrollInssElection.objects.filter(period=period, employee=employee)
            .values_list("elected_has_inss", flat=True)
            .first()
        )
        if elected is not None:
            return bool(elected)
        if EmployeeInssEnrollment.objects.filter(employee=employee).exists():
            return EmployeeInssEnrollment.resolve_for(employee, period.start_date) == InssRegime.AFFILIATED
    # (2) Continuidad desde la última planilla registrada del empleado.
    last_has_inss = (
        PayrollEntry.objects.filter(employee=employee)
        .order_by("-sheet__period__year", "-sheet__period__month", "-id")
        .values_list("has_inss", flat=True)
        .first()
    )
    if last_has_inss is not None:
        return bool(last_has_inss)
    return None


def consolidate_field_attendance(
    *,
    request,
    actor,
    work_day: FieldWorkDay,
    payroll_period: PayrollPeriod | None = None,
) -> list[FieldAttendanceConsolidation]:
    """Materializa el estado por empleado/dia desde lista, reportes, eventos y traslados."""
    _validate_work_day_mutable(work_day)
    period = payroll_period or work_day.payroll_period
    _validate_period_scope(company=work_day.company, payroll_period=period, work_date=work_day.work_date)
    if FieldAttendanceConsolidation.objects.filter(
        work_day=work_day,
        status__in=[
            FieldAttendanceConsolidationStatus.APPROVED,
            FieldAttendanceConsolidationStatus.LOCKED_FOR_PAYROLL,
        ],
    ).exists():
        raise _field_error("invalid_state", "La consolidacion aprobada o bloqueada no se recalcula directamente.")

    rollcall_by_employee = {
        line.employee_id: line
        for line in FieldRollCallLine.objects.select_related("employee", "rollcall").filter(rollcall__work_day=work_day)
    }
    crew_lines_by_employee: dict[int, list[FieldCrewReportLine]] = defaultdict(list)
    for line in FieldCrewReportLine.objects.select_related("employee", "report__crew").filter(report__crew__work_day=work_day):
        crew_lines_by_employee[line.employee_id].append(line)
    events_by_employee: dict[int, list[FieldWorkerEvent]] = defaultdict(list)
    for event in FieldWorkerEvent.objects.select_related("employee").filter(work_day=work_day):
        events_by_employee[event.employee_id].append(event)
    transfers_by_employee: dict[int, list[FieldTransfer]] = defaultdict(list)
    for transfer in FieldTransfer.objects.select_related("employee", "from_crew", "to_crew").filter(work_day=work_day):
        transfers_by_employee[transfer.employee_id].append(transfer)

    employee_ids = (
        set(rollcall_by_employee)
        | set(crew_lines_by_employee)
        | set(events_by_employee)
        | set(transfers_by_employee)
    )

    with transaction.atomic():
        if employee_ids:
            FieldAttendanceConsolidation.objects.filter(work_day=work_day).exclude(employee_id__in=employee_ids).delete()
        else:
            FieldAttendanceConsolidation.objects.filter(work_day=work_day).delete()

        consolidations: list[FieldAttendanceConsolidation] = []
        conflict_count = 0
        warning_count = 0
        for employee_id in sorted(employee_ids):
            roll_line = rollcall_by_employee.get(employee_id)
            crew_lines = crew_lines_by_employee.get(employee_id, [])
            worker_events = events_by_employee.get(employee_id, [])
            transfers = transfers_by_employee.get(employee_id, [])
            crew_ids = {line.report.crew_id for line in crew_lines}
            event_types = {line.event_type for line in crew_lines} | {event.event_type for event in worker_events}
            rollcall_status = roll_line.status if roll_line else None

            conflict_codes: list[str] = []
            status = FieldAttendanceConsolidationStatus.OK

            if len(crew_ids) > 1:
                if _has_transfer_between(crew_ids, transfers):
                    conflict_codes.append("TRANSFERRED_BETWEEN_CREWS")
                    status = FieldAttendanceConsolidationStatus.WARNING
                else:
                    conflict_codes.append("DUPLICATE_CREW_WITHOUT_TRANSFER")
                    status = FieldAttendanceConsolidationStatus.BLOCKED

            crew_has_presence = bool(event_types & FIELD_PRESENT_EVENTS)
            if rollcall_status == FieldRollCallLineStatus.ABSENT and crew_has_presence:
                conflict_codes.append("ROLLCALL_ABSENT_CREW_PRESENT")
                if status != FieldAttendanceConsolidationStatus.BLOCKED:
                    status = FieldAttendanceConsolidationStatus.CONFLICT

            if rollcall_status == FieldRollCallLineStatus.PRESENT and not crew_lines and status == FieldAttendanceConsolidationStatus.OK:
                conflict_codes.append("MISSING_CREW_CONFIRMATION")
                status = FieldAttendanceConsolidationStatus.WARNING

            if roll_line is None and crew_lines and status == FieldAttendanceConsolidationStatus.OK:
                conflict_codes.append("MISSING_ROLLCALL_CONFIRMATION")
                status = FieldAttendanceConsolidationStatus.WARNING

            primary_event_type = _primary_event(event_types, rollcall_status=rollcall_status)
            day_value = _calculate_day_value(
                primary_event_type=primary_event_type,
                rollcall_status=rollcall_status,
                crew_lines=crew_lines,
                is_split_transfer="TRANSFERRED_BETWEEN_CREWS" in conflict_codes,
            )
            employee = (
                roll_line.employee if roll_line
                else crew_lines[0].employee if crew_lines
                else worker_events[0].employee if worker_events
                else transfers[0].employee
            )
            source_summary = {
                "rollcall_status": rollcall_status,
                "crew_ids": sorted(crew_ids),
                "crew_report_line_ids": [line.id for line in crew_lines],
                "event_ids": [event.id for event in worker_events],
                "transfer_ids": [transfer.id for transfer in transfers],
            }
            consolidation, _ = FieldAttendanceConsolidation.objects.update_or_create(
                work_day=work_day,
                employee=employee,
                defaults={
                    "payroll_period": period,
                    "status": status,
                    "day_value": day_value,
                    "primary_event_type": primary_event_type,
                    "conflict_codes": conflict_codes,
                    "source_summary": source_summary,
                    "has_inss_snapshot": resolve_worker_inss(employee, period=period),
                },
            )
            consolidations.append(consolidation)
            if status in {FieldAttendanceConsolidationStatus.CONFLICT, FieldAttendanceConsolidationStatus.BLOCKED}:
                conflict_count += 1
                _audit(
                    request=request,
                    actor=actor,
                    event_type="FIELD_ATTENDANCE_CONFLICT_RAISED",
                    subject_type="FIELD_ATTENDANCE_CONSOLIDATION",
                    subject_id=consolidation.id,
                    metadata={
                        "work_day_id": work_day.id,
                        "employee_id": employee_id,
                        "status": status,
                        "conflict_codes": conflict_codes,
                    },
                )
            elif status == FieldAttendanceConsolidationStatus.WARNING:
                warning_count += 1

        if work_day.status != FieldWorkDayStatus.IN_REVIEW:
            work_day.status = FieldWorkDayStatus.IN_REVIEW
            work_day.save(update_fields=["status", "updated_at"])
        _audit(
            request=request,
            actor=actor,
            event_type="FIELD_ATTENDANCE_CONSOLIDATED",
            subject_type="FIELD_WORK_DAY",
            subject_id=work_day.id,
            metadata={
                "payroll_period_id": period.id if period else None,
                "employee_count": len(consolidations),
                "conflict_count": conflict_count,
                "warning_count": warning_count,
            },
        )
    return consolidations


def approve_field_attendance(
    *,
    request,
    actor,
    work_day: FieldWorkDay,
) -> list[FieldAttendanceConsolidation]:
    """Aprueba la consolidacion del dia si no hay conflictos bloqueantes."""
    if work_day.status == FieldWorkDayStatus.LOCKED:
        raise _field_error("invalid_state", "El dia de campo bloqueado no admite aprobacion directa.")
    blocked = FieldAttendanceConsolidation.objects.filter(
        work_day=work_day,
        status__in=[FieldAttendanceConsolidationStatus.CONFLICT, FieldAttendanceConsolidationStatus.BLOCKED],
    )
    if blocked.exists():
        raise _field_error(
            "blocked_conflict",
            "No se puede aprobar asistencia de campo con conflictos o bloqueos.",
            context={"work_day_id": work_day.id, "blocked_count": blocked.count()},
        )
    eligible = FieldAttendanceConsolidation.objects.filter(
        work_day=work_day,
        status__in=[FieldAttendanceConsolidationStatus.OK, FieldAttendanceConsolidationStatus.WARNING],
    )
    if not eligible.exists():
        raise _field_error("invalid_state", "No hay consolidaciones listas para aprobar.")

    now = timezone.now()
    approved_count = eligible.count()
    with transaction.atomic():
        eligible.update(status=FieldAttendanceConsolidationStatus.APPROVED, approved_by=actor, approved_at=now)
        work_day.status = FieldWorkDayStatus.APPROVED
        work_day.approved_by = actor
        work_day.approved_at = now
        work_day.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
        _audit(
            request=request,
            actor=actor,
            event_type="FIELD_ATTENDANCE_APPROVED",
            subject_type="FIELD_WORK_DAY",
            subject_id=work_day.id,
            metadata={"approved_count": approved_count},
        )
    return list(FieldAttendanceConsolidation.objects.filter(work_day=work_day).order_by("employee_id"))


# ---------------------------------------------------------------------------
# Puente asistencia de campo → planilla (PayrollEntry)
# ---------------------------------------------------------------------------

# Días que suman como trabajados (el día partido ya viene como day_value 0.5).
_FIELD_SUBSIDY_EVENTS = {FieldWorkerEventType.SICK, FieldWorkerEventType.ACCIDENT}


def aggregate_attendance_for_employee(*, period: PayrollPeriod, employee) -> dict:
    """Agrega la asistencia APROBADA del empleado en el período a días de planilla.

    Mapeo (lo que la nómina necesita):
      - PRESENT / medio día / traslado → days_worked (suma day_value; medio día = 0.5)
      - SICK / ACCIDENT                 → days_subsidy (día de subsidio INSS)
      - ABSENT / PERMISSION / ...       → no suman (day_value 0)
      - día trabajado en domingo        → sunday_worked_days
      - séptimo día (por semana calendario): se gana 1 si la semana tuvo trabajo y
        NO hubo falta INJUSTIFICADA (ABSENT). Subsidio/permiso/vacación NO la rompen.
    """
    consolidations = FieldAttendanceConsolidation.objects.filter(
        payroll_period=period,
        employee=employee,
        status__in=[
            FieldAttendanceConsolidationStatus.APPROVED,
            FieldAttendanceConsolidationStatus.LOCKED_FOR_PAYROLL,
        ],
    ).select_related("work_day")

    days_worked = Decimal("0.00")
    days_subsidy = Decimal("0.00")
    sunday_worked_days = 0
    count = 0
    weeks: dict[tuple, dict] = defaultdict(lambda: {"worked": False, "unjustified_absence": False})
    for cons in consolidations:
        count += 1
        wk = cons.work_day.work_date.isocalendar()[:2]  # (año ISO, semana ISO)
        if cons.primary_event_type == FieldWorkerEventType.ABSENT:
            weeks[wk]["unjustified_absence"] = True
        if cons.primary_event_type in _FIELD_SUBSIDY_EVENTS:
            days_subsidy += Decimal("1.00")
            continue
        days_worked += cons.day_value
        if cons.day_value > 0:
            weeks[wk]["worked"] = True
            if cons.work_day.work_date.weekday() == 6:  # 6 = domingo
                sunday_worked_days += 1
    seventh_day_days = sum(1 for w in weeks.values() if w["worked"] and not w["unjustified_absence"])
    return {
        "days_worked": days_worked.quantize(Decimal("0.01")),
        "days_subsidy": days_subsidy.quantize(Decimal("0.01")),
        "sunday_worked_days": sunday_worked_days,
        "seventh_day_days": Decimal(seventh_day_days).quantize(Decimal("0.01")),
        "consolidation_count": count,
    }


def apply_field_attendance_to_entry(*, request, actor, entry: PayrollEntry) -> PayrollEntry:
    """Empuja la asistencia APROBADA del empleado a su línea de planilla y recalcula.

    Cierra el hueco de los días tipeados a mano: los días salen de la asistencia
    aprobada, no del input crudo. Bloquea las consolidaciones aplicadas
    (LOCKED_FOR_PAYROLL) para que no se recalculen después de entrar a planilla.
    """
    if entry.employee_id is None:
        raise _field_error("missing_employee", "La línea de planilla no tiene empleado para tomar asistencia.")
    period = entry.sheet.period
    agg = aggregate_attendance_for_employee(period=period, employee=entry.employee)
    if agg["consolidation_count"] == 0:
        raise _field_error(
            "no_attendance",
            "No hay asistencia de campo aprobada para este empleado en el período.",
            context={"entry_id": entry.id, "employee_id": entry.employee_id},
        )

    with transaction.atomic():
        entry.days_worked = agg["days_worked"]
        entry.days_subsidy = agg["days_subsidy"]
        entry.sunday_worked_days = agg["sunday_worked_days"]
        entry.seventh_day_days = agg["seventh_day_days"]
        entry = compute_entry(entry=entry)

        FieldAttendanceConsolidation.objects.filter(
            payroll_period=period,
            employee=entry.employee,
            status=FieldAttendanceConsolidationStatus.APPROVED,
        ).update(status=FieldAttendanceConsolidationStatus.LOCKED_FOR_PAYROLL, locked_at=timezone.now())

        _audit(
            request=request,
            actor=actor,
            event_type="FIELD_ATTENDANCE_APPLIED_TO_PAYROLL",
            subject_type="PAYROLL_ENTRY",
            subject_id=entry.id,
            metadata={
                "period_id": period.id,
                "employee_id": entry.employee_id,
                "days_worked": str(agg["days_worked"]),
                "days_subsidy": str(agg["days_subsidy"]),
                "sunday_worked_days": agg["sunday_worked_days"],
            },
        )
    return entry


def apply_field_attendance_to_sheet(*, request, actor, sheet: PayrollSheet) -> dict:
    """Aplica la asistencia aprobada a todas las líneas de la planilla con asistencia disponible."""
    applied: list[int] = []
    skipped: list[int] = []
    for entry in sheet.entries.select_related("employee", "sheet__period").all():
        try:
            apply_field_attendance_to_entry(request=request, actor=actor, entry=entry)
            applied.append(entry.id)
        except FieldAttendanceError:
            skipped.append(entry.id)
    return {"applied": applied, "skipped": skipped}


# ---------------------------------------------------------------------------
# Rollup asistencia de campo → AttendanceReport (reporte legal de período)
# ---------------------------------------------------------------------------

# Eventos que cuentan como día trabajado (el medio día ya viene en day_value).
_FIELD_WORKED_EVENTS = {
    FieldWorkerEventType.PRESENT,
    FieldWorkerEventType.LEFT_EARLY,
    FieldWorkerEventType.JOINED_LATE,
    FieldWorkerEventType.TRANSFERRED,
}

_ROLLUP_CONSOLIDATION_STATES = [
    FieldAttendanceConsolidationStatus.APPROVED,
    FieldAttendanceConsolidationStatus.LOCKED_FOR_PAYROLL,
]


def aggregate_attendance_report_detail(*, period: PayrollPeriod, employee) -> dict:
    """Desglose detallado de la asistencia de campo APROBADA para el reporte legal.

    A diferencia de ``aggregate_attendance_for_employee`` (que agrupa para la planilla),
    separa cada tipo de evento en su casilla del AttendanceReport. Mantiene la misma
    clasificación de "día trabajado" (PRESENT/medio día/traslado) y de "subsidio"
    (SICK/ACCIDENT) que el puente a planilla, para no desviarse de la planilla.
    """
    consolidations = FieldAttendanceConsolidation.objects.filter(
        payroll_period=period,
        employee=employee,
        status__in=_ROLLUP_CONSOLIDATION_STATES,
    ).select_related("work_day")

    detail: dict = {
        "days_worked": Decimal("0.00"),
        "days_absent": Decimal("0.00"),
        "days_sick": Decimal("0.00"),
        "days_accident": Decimal("0.00"),
        "days_subsidy": Decimal("0.00"),
        "days_transferred": Decimal("0.00"),
        "sunday_worked_days": 0,
        "count": 0,
        "branch_ids": set(),
    }
    for cons in consolidations:
        detail["count"] += 1
        detail["branch_ids"].add(cons.work_day.branch_id)
        event_type = cons.primary_event_type
        if event_type == FieldWorkerEventType.SICK:
            detail["days_sick"] += Decimal("1.00")
            detail["days_subsidy"] += Decimal("1.00")
        elif event_type == FieldWorkerEventType.ACCIDENT:
            detail["days_accident"] += Decimal("1.00")
            detail["days_subsidy"] += Decimal("1.00")
        elif event_type == FieldWorkerEventType.ABSENT:
            detail["days_absent"] += Decimal("1.00")
        elif event_type in _FIELD_WORKED_EVENTS:
            detail["days_worked"] += cons.day_value
            if event_type == FieldWorkerEventType.TRANSFERRED:
                detail["days_transferred"] += cons.day_value
            if cons.day_value > 0 and cons.work_day.work_date.weekday() == 6:  # 6 = domingo
                detail["sunday_worked_days"] += 1
        # PERMISSION / DISMISSED / OTHER: no suman a una casilla de días.
    for key in ("days_worked", "days_absent", "days_sick", "days_accident",
                "days_subsidy", "days_transferred"):
        detail[key] = detail[key].quantize(Decimal("0.01"))
    return detail


def rollup_field_attendance_report(*, request, actor, period: PayrollPeriod, employee) -> AttendanceReport:
    """Deriva (o actualiza) el AttendanceReport de campo de un empleado para el período.

    Des-huerfaniza AttendanceReport: toma la asistencia de campo consolidada y aprobada
    y la cuaja en el reporte legal de período (fuente FIELD). Idempotente por
    (período, empleado, fuente): re-ejecutar actualiza el mismo reporte.
    """
    detail = aggregate_attendance_report_detail(period=period, employee=employee)
    if detail["count"] == 0:
        raise _field_error(
            "no_attendance",
            "No hay asistencia de campo aprobada para este empleado en el período.",
            context={"period_id": period.id, "employee_id": getattr(employee, "id", None)},
        )

    branch_ids = {b for b in detail["branch_ids"] if b is not None}
    branch_id = branch_ids.pop() if len(branch_ids) == 1 else None
    now = timezone.now()
    with transaction.atomic():
        report, _created = AttendanceReport.objects.update_or_create(
            period=period,
            employee=employee,
            source=AttendanceSource.FIELD,
            defaults={
                "company": period.company,
                "branch_id": branch_id,
                "employee_name": getattr(employee, "full_name", "") or "",
                "status": AttendanceStatus.SUBMITTED,
                "days_worked": detail["days_worked"],
                "days_absent": detail["days_absent"],
                "days_sick": detail["days_sick"],
                "days_accident": detail["days_accident"],
                "days_subsidy": detail["days_subsidy"],
                "days_transferred": detail["days_transferred"],
                "sunday_worked_days": detail["sunday_worked_days"],
                "has_conflict": False,
                "submitted_by": actor,
                "submitted_at": now,
            },
        )
        _audit(
            request=request,
            actor=actor,
            event_type="FIELD_ATTENDANCE_REPORT_ROLLUP",
            subject_type="ATTENDANCE_REPORT",
            subject_id=report.id,
            metadata={
                "period_id": period.id,
                "employee_id": getattr(employee, "id", None),
                "days_worked": str(detail["days_worked"]),
                "consolidation_count": detail["count"],
            },
        )
    return report


def rollup_field_attendance_reports_for_period(
    *, request, actor, period: PayrollPeriod,
) -> list[AttendanceReport]:
    """Rollup de todos los empleados con asistencia de campo aprobada en el período."""
    employees: dict = {}
    rows = (
        FieldAttendanceConsolidation.objects.filter(
            payroll_period=period,
            status__in=_ROLLUP_CONSOLIDATION_STATES,
        )
        .select_related("employee")
        .order_by("employee_id")
    )
    for cons in rows:
        employees.setdefault(cons.employee_id, cons.employee)
    return [
        rollup_field_attendance_report(request=request, actor=actor, period=period, employee=employee)
        for employee in employees.values()
    ]


# ---------------------------------------------------------------------------
# Calendario de feriados — resolución por período
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ResolvedHoliday:
    """Un feriado del catálogo materializado a una fecha concreta dentro de un período."""
    date: _date
    holiday_id: int
    code: str
    name: str
    legal_type: str
    locality: str
    applies_to_payroll: bool
    pays_premium: bool
    premium_rate: Decimal | None


def holidays_for_period(
    period: PayrollPeriod,
    *,
    only_payroll: bool = False,
    include_company_specific: bool = True,
) -> list[ResolvedHoliday]:
    """Feriados del catálogo que caen dentro del rango [start_date, end_date] del período.

    Es lo que permite al revisor de la planilla *ubicar* los días feriados precargados.
    No auto-resuelve por geografía: devuelve todos los aplicables (catálogo nacional +
    feriados propios de la empresa) y el revisor decide cuáles cuentan.

    - ``only_payroll``: solo los que por defecto cuentan para la planilla
      (excluye asuetos estatales no adoptados).
    - ``include_company_specific``: incluir feriados propios de la empresa del período
      además del catálogo nacional compartido (``company`` NULL).
    """
    if period.start_date is None or period.end_date is None:
        return []

    qs = Holiday.objects.filter(is_active=True)
    if include_company_specific and period.company_id is not None:
        qs = qs.filter(Q(company__isnull=True) | Q(company_id=period.company_id))
    else:
        qs = qs.filter(company__isnull=True)
    if only_payroll:
        qs = qs.filter(applies_to_payroll=True)

    years = range(period.start_date.year, period.end_date.year + 1)
    resolved: list[ResolvedHoliday] = []
    for holiday in qs:
        for year in years:
            holiday_date = holiday.date_for_year(year)
            if holiday_date is None or not (period.start_date <= holiday_date <= period.end_date):
                continue
            resolved.append(ResolvedHoliday(
                date=holiday_date,
                holiday_id=holiday.id,
                code=holiday.code,
                name=holiday.name,
                legal_type=holiday.legal_type,
                locality=holiday.locality,
                applies_to_payroll=holiday.applies_to_payroll,
                pays_premium=holiday.pays_premium,
                premium_rate=holiday.premium_rate,
            ))
    resolved.sort(key=lambda r: (r.date, r.name))
    return resolved


def holiday_dates_for_period(period: PayrollPeriod, *, only_payroll: bool = True) -> set[_date]:
    """Conjunto de fechas feriadas del período (para cruzar con la asistencia)."""
    return {r.date for r in holidays_for_period(period, only_payroll=only_payroll)}
