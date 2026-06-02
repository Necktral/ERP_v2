from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.modulos.audit.writer import write_event
from apps.modulos.iam.models import OrgUnit

from .models import (
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
    cfg = NominaConfig.get_active(company=company, date=start_date)
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
