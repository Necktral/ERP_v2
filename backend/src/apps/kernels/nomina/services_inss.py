"""Servicios de régimen INSS (el "dolor de cabeza" de nómina).

Resuelve los trabajadores que cotizan INSS un período y al siguiente no, sin el shuffle
manual entre planillas "CON INSS" / "SIN INSS":

- `set_employee_inss_enrollment`: afiliación maestra fechada (effective-dated).
- `set_period_inss_election`: override auditado de un período.
- `resolve_period_inss_elections`: materializa la elección por afiliación para cada empleado.
- `classify_entries_by_inss`: auto-clasifica cada PayrollEntry a la planilla CON/SIN INSS
  correcta y recalcula.
"""
from __future__ import annotations

from datetime import timedelta

from django.db import transaction

from apps.modulos.audit.writer import write_event

from .models import (
    EmployeeInssEnrollment,
    InssElectionSource,
    InssRegime,
    PayrollEntry,
    PayrollInssElection,
    PayrollPeriod,
    PayrollSheet,
)
from .services import compute_entry


def set_employee_inss_enrollment(
    *, request, actor, employee, regime: str, effective_from, reason: str = ""
) -> EmployeeInssEnrollment:
    """Cambia el régimen INSS del empleado: cierra la afiliación abierta previa y crea la nueva."""
    with transaction.atomic():
        prev = (
            EmployeeInssEnrollment.objects.select_for_update()
            .filter(employee=employee, effective_to__isnull=True, effective_from__lt=effective_from)
            .order_by("-effective_from")
            .first()
        )
        if prev is not None:
            prev.effective_to = effective_from - timedelta(days=1)
            prev.save(update_fields=["effective_to"])

        enrollment = EmployeeInssEnrollment.objects.create(
            company=employee.company,
            employee=employee,
            regime=regime,
            effective_from=effective_from,
            reason=reason or "",
            created_by=actor,
        )
        write_event(
            request=request,
            module="NOMINA",
            event_type="NOMINA_EMPLOYEE_INSS_REGIME_CHANGED",
            reason_code="NOMINA_OK",
            actor_user=actor,
            subject_type="EMPLOYEE_INSS_ENROLLMENT",
            subject_id=str(enrollment.id),
            after_snapshot={
                "employee_id": employee.id,
                "regime": regime,
                "effective_from": str(effective_from),
            },
            metadata={"company_id": str(employee.company_id), "employee_id": employee.id},
        )
        return enrollment


def set_period_inss_election(
    *, request, actor, period: PayrollPeriod, employee=None, cedula: str = "", elected_has_inss: bool, reason: str = ""
) -> PayrollInssElection:
    """Override auditado de la elección INSS de un período (source=OVERRIDE)."""
    with transaction.atomic():
        if employee is not None:
            election = PayrollInssElection.objects.filter(period=period, employee=employee).first()
        else:
            election = PayrollInssElection.objects.filter(
                period=period, employee__isnull=True, cedula=cedula
            ).first()
        if election is None:
            election = PayrollInssElection(period=period, employee=employee, cedula=cedula or "")
        election.elected_has_inss = elected_has_inss
        election.source = InssElectionSource.OVERRIDE
        election.reason = reason or ""
        if election.created_by_id is None:
            election.created_by = actor
        election.save()

        write_event(
            request=request,
            module="NOMINA",
            event_type="NOMINA_INSS_ELECTION_SET",
            reason_code="NOMINA_OK",
            actor_user=actor,
            subject_type="PAYROLL_INSS_ELECTION",
            subject_id=str(election.id),
            after_snapshot={
                "period_id": period.id,
                "employee_id": getattr(employee, "id", None),
                "cedula": cedula or "",
                "elected_has_inss": elected_has_inss,
                "source": InssElectionSource.OVERRIDE,
            },
            metadata={"period_id": period.id},
        )
        return election


def resolve_period_inss_elections(*, request, actor, period: PayrollPeriod) -> dict[int, bool]:
    """Para cada empleado con entry en el período, crea la elección por afiliación si no hay override.

    Devuelve {employee_id -> elected_has_inss}.
    """
    employee_ids = list(
        PayrollEntry.objects.filter(sheet__period=period, employee__isnull=False)
        .values_list("employee_id", flat=True)
        .distinct()
    )
    elections: dict[int, bool] = {}
    with transaction.atomic():
        for emp_id in employee_ids:
            existing = PayrollInssElection.objects.filter(period=period, employee_id=emp_id).first()
            if existing is not None:
                elections[emp_id] = existing.elected_has_inss
                continue
            regime = EmployeeInssEnrollment.resolve_for(emp_id, period.start_date)
            elected = regime == InssRegime.AFFILIATED
            PayrollInssElection.objects.create(
                period=period,
                employee_id=emp_id,
                elected_has_inss=elected,
                source=InssElectionSource.ENROLLMENT,
                created_by=actor,
            )
            elections[emp_id] = elected
    return elections


def _base_sheet_name(name: str) -> str:
    for suffix in (" CON INSS", " SIN INSS"):
        if name.endswith(suffix):
            return name[: -len(suffix)].strip()
    return name.strip()


def _sibling_sheet(period: PayrollPeriod, branch, base_name: str, has_inss: bool) -> PayrollSheet:
    label = "CON INSS" if has_inss else "SIN INSS"
    name = f"{base_name} {label}".strip() if base_name else label
    sheet = PayrollSheet.objects.filter(
        period=period, branch=branch, has_inss=has_inss, sheet_name=name
    ).first()
    if sheet is None:
        sheet = PayrollSheet.objects.create(period=period, branch=branch, has_inss=has_inss, sheet_name=name)
    return sheet


def classify_entries_by_inss(*, request, actor, period: PayrollPeriod) -> dict:
    """Auto-clasifica cada entry a la planilla CON/SIN INSS correcta y recalcula.

    Elimina el shuffle manual: fija `entry.has_inss` desde la elección resuelta y, si la
    planilla destino no coincide, MUEVE el entry a la hoja hermana (la crea si no existe).
    """
    elections = resolve_period_inss_elections(request=request, actor=actor, period=period)
    updated = 0
    moved = 0
    with transaction.atomic():
        entries = (
            PayrollEntry.objects.select_related("sheet")
            .filter(sheet__period=period, employee__isnull=False)
        )
        for entry in entries:
            elected = elections.get(entry.employee_id)
            if elected is None:
                continue
            changed = False
            if entry.has_inss != elected:
                entry.has_inss = elected
                changed = True
            if entry.sheet.has_inss != elected:
                base = _base_sheet_name(entry.sheet.sheet_name)
                entry.sheet = _sibling_sheet(period, entry.sheet.branch, base, elected)
                changed = True
                moved += 1
            if changed:
                compute_entry(entry=entry)  # recalcula y guarda (incl. sheet/has_inss)
                updated += 1

        write_event(
            request=request,
            module="NOMINA",
            event_type="NOMINA_ENTRIES_RECLASSIFIED",
            reason_code="NOMINA_OK",
            actor_user=actor,
            subject_type="PAYROLL_PERIOD",
            subject_id=str(period.id),
            metadata={"period_id": period.id, "updated": updated, "moved": moved},
        )
    return {"updated": updated, "moved": moved, "elections": elections}
