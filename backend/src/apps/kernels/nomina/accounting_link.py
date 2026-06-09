"""Puente nómina → contabilidad (U4).

Al aprobar el período, consolida los totales de las líneas de planilla, emite el outbox
`PayrollPeriodApproved` y lo enlaza al motor de posting (best-effort, igual que facturación):
genera el asiento del costo de planilla como `JournalDraft`. Nunca bloquea la aprobación.
"""
from __future__ import annotations

from decimal import Decimal

from django.db.models import Sum

from apps.modulos.audit.writer import write_event
from apps.modulos.integration.models import OutboxEvent
from apps.modulos.integration.services import publish_outbox_event

from .models import PayrollEntry, PayrollPeriod


def _d(value) -> Decimal:
    return Decimal(str(value or "0"))


def post_payroll_period_to_accounting(*, request, actor, period: PayrollPeriod) -> dict:
    """Consolida totales del período, emite el outbox y enlaza a contabilidad (best-effort)."""
    # NM-04: idempotencia por período. El kernel de contabilidad dedupe por
    # `source_outbox_event_id`, así que el doble-posteo solo puede venir de emitir
    # un SEGUNDO outbox `PayrollPeriodApproved` para el mismo período → aquí se evita.
    already = (
        OutboxEvent.objects.filter(
            source_module="NOMINA",
            event_type="PayrollPeriodApproved",
            company=period.company,
            payload__data__period_id=period.id,
        )
        .order_by("id")
        .first()
    )
    if already is not None:
        return {
            "outbox_event_id": str(already.event_id),
            "journal_draft_id": None,
            "link_status": "ALREADY_POSTED",
        }

    agg = PayrollEntry.objects.filter(sheet__period=period).aggregate(
        devengado=Sum("total_devengado"),
        income=Sum("total_income"),
        vacation=Sum("vacation_provision"),
        thirteenth=Sum("thirteenth_month_provision"),
        inss_patronal=Sum("inss_patronal"),
        inatec=Sum("inatec"),
        inss_laboral=Sum("inss_laboral"),
        ir=Sum("ir_amount"),
        net=Sum("net_to_pay"),
        deductions=Sum("total_deductions"),
        employer_cost=Sum("total_employer_cost"),
        payroll_cost=Sum("total_payroll_cost"),
        loan=Sum("loan_payment"),
        food=Sum("food_deduction"),
        advance=Sum("advance_deduction"),
        store=Sum("store_credit_deduction"),
        other=Sum("other_deductions"),
    )
    employee_deductions = (
        _d(agg["loan"]) + _d(agg["food"]) + _d(agg["advance"]) + _d(agg["store"]) + _d(agg["other"])
    )

    # Rollup al registro del período.
    period.total_gross = _d(agg["income"])
    period.total_deductions = _d(agg["deductions"])
    period.total_net = _d(agg["net"])
    period.total_patronal = _d(agg["employer_cost"])
    period.total_payroll_cost = _d(agg["payroll_cost"])
    period.save(
        update_fields=[
            "total_gross", "total_deductions", "total_net",
            "total_patronal", "total_payroll_cost", "updated_at",
        ]
    )

    # Agregados que consume la regla de posting (data.<clave>).
    payload = {
        "period_id": period.id,
        "total_devengado": str(_d(agg["devengado"])),
        "total_vacation": str(_d(agg["vacation"])),
        "total_thirteenth": str(_d(agg["thirteenth"])),
        "total_inss_patronal": str(_d(agg["inss_patronal"])),
        "total_inatec": str(_d(agg["inatec"])),
        "total_inss_laboral": str(_d(agg["inss_laboral"])),
        "total_ir": str(_d(agg["ir"])),
        "total_employee_deductions": str(employee_deductions),
        "total_net": str(_d(agg["net"])),
    }
    outbox = publish_outbox_event(
        source_module="NOMINA",
        event_type="PayrollPeriodApproved",
        payload=payload,
        company=period.company,
        actor_user=actor,
        request=request,
    )

    journal_draft_id = None
    link_status = "SKIPPED"
    try:
        from apps.kernels.accounting.services import (
            apply_accounting_link_to_outbox_event,
            link_operational_event_to_accounting,
        )

        link = link_operational_event_to_accounting(outbox_event=outbox, actor_user=actor)
        apply_accounting_link_to_outbox_event(outbox_event=outbox, link=link)
        journal_draft_id = link.journal_draft_id
        link_status = link.status
    except (ImportError, AttributeError, RuntimeError, ValueError, KeyError, TypeError):
        # Best-effort: la contabilidad nunca bloquea la aprobación de la planilla.
        link_status = "FAILED"

    write_event(
        request=request,
        module="NOMINA",
        event_type="NOMINA_PAYROLL_POSTED",
        reason_code="NOMINA_OK",
        actor_user=actor,
        subject_type="PAYROLL_PERIOD",
        subject_id=str(period.id),
        metadata={"period_id": period.id, "journal_draft_id": journal_draft_id, "link_status": link_status},
    )
    return {
        "outbox_event_id": str(outbox.event_id),
        "journal_draft_id": journal_draft_id,
        "link_status": link_status,
    }
