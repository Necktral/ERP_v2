"""Lazo de cobro del empleado: comisariato → planilla (sala de pago).

El comisariato manda sus cuentas por cobrar a la sala de pago: para cada empleado de
la planilla con CxC abierta en el comisariato, se fija la columna existente
`PayrollEntry.store_credit_deduction` y se **abona** la CxC por el riel probado
`register_payroll_loan_deduction` (nómina → portfolio). El cruce entre empresas usa la
**cédula** como clave natural (la planilla está en la finca; la CxC está en el
comisariato, que es OTRA empresa → el empleado es un Party distinto por empresa).

Dirección de dependencia: modulo (comisariato) → kernel (nomina/portfolio), la preferida.

FASE 2 (pendiente, NO en v1): el reclass intercompany finca→comisariato (cobro-en-nombre-de).
Como toda empresa tiene RUC propio, cuando la finca retiene de la planilla efectivo que es
del comisariato, debe nacer una CxP-IC de la finca al comisariato y reclasificarse la CxC del
empleado a CxC-finca en el comisariato. Eso es un primitivo NUEVO de tesorería entre empresas
(cobro-en-nombre-de), distinto de `record_intercompany_charge` (que postea ingreso/gasto, no
aplica a un cobro por cuenta). v1 abona la CxC directo y difiere ese asiento.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from django.db import transaction

from apps.kernels.nomina.models import PayrollEntry, PayrollSheet, SheetStatus
from apps.kernels.nomina.portfolio_link import register_payroll_loan_deduction
from apps.kernels.portfolio.models import Receivable
from apps.modulos.audit.writer import write_event
from apps.modulos.iam.models import OrgUnit

from .models import CustomerCreditAccount, CustomerSegment
from .services import TERMINAL_STATUSES, ComisariatoError, _q2

EDITABLE_SHEET_STATUSES = {SheetStatus.DRAFT, SheetStatus.SUBMITTED}


def _open_receivables(*, company: OrgUnit, party) -> list[Receivable]:
    return list(
        Receivable.objects.filter(company=company, party=party)
        .exclude(status__in=TERMINAL_STATUSES)
        .order_by("issue_date", "id")
    )


def apply_store_credit_deductions(
    *,
    request,
    actor,
    sheet: PayrollSheet,
    comisariato_company: OrgUnit,
    per_period_cap: Optional[Decimal] = None,
) -> dict[str, Any]:
    """Aplica el crédito del comisariato a la planilla (descuento + abono de CxC).

    Para cada `PayrollEntry` cuyo empleado (por cédula) tenga cuenta EMPLOYEE con CxC
    abierta en el comisariato: fija `store_credit_deduction = min(saldo, neto disponible,
    tope)`, recomputa totales y abona las CxC (FIFO). Best-effort por entrada: una falla no
    aborta el resto. Idempotente: omite entradas que ya tienen `store_credit_deduction > 0`.
    """
    if sheet.status not in EDITABLE_SHEET_STATUSES:
        raise ComisariatoError("COMISARIATO_SHEET_NOT_EDITABLE")
    cap = _q2(per_period_cap) if per_period_cap is not None else None

    accounts = (
        CustomerCreditAccount.objects
        .filter(company=comisariato_company, segment=CustomerSegment.EMPLOYEE, is_active=True)
        .select_related("party")
    )
    by_cedula: dict[str, CustomerCreditAccount] = {
        a.party.national_id.strip().upper(): a for a in accounts if a.party.national_id
    }

    results: list[dict[str, Any]] = []
    for entry in PayrollEntry.objects.filter(sheet=sheet):
        ced = (entry.cedula or "").strip().upper()
        if not ced:
            continue
        account = by_cedula.get(ced)
        if account is None:
            continue
        if entry.store_credit_deduction and entry.store_credit_deduction > 0:
            results.append({"entry_id": entry.id, "status": "SKIPPED_ALREADY"})
            continue

        open_recs = _open_receivables(company=comisariato_company, party=account.party)
        outstanding = _q2(sum((r.outstanding_amount for r in open_recs), Decimal("0.00")))
        if outstanding <= 0:
            continue

        other_ded = (
            entry.inss_laboral + entry.ir_amount + entry.loan_payment
            + entry.food_deduction + entry.advance_deduction + entry.other_deductions
        )
        net_before = _q2(entry.total_devengado - other_ded)
        due = min(outstanding, net_before if net_before > 0 else Decimal("0.00"))
        if cap is not None:
            due = min(due, cap)
        due = _q2(due)
        if due <= 0:
            results.append({"entry_id": entry.id, "status": "SKIPPED_NO_NET"})
            continue

        try:
            with transaction.atomic():
                entry.store_credit_deduction = due
                entry.total_deductions = _q2(other_ded + due)
                entry.net_to_pay = _q2(entry.total_devengado - entry.total_deductions)
                entry.save(update_fields=["store_credit_deduction", "total_deductions", "net_to_pay"])

                remaining = due
                abonos: list[dict[str, str]] = []
                for rec in open_recs:
                    if remaining <= 0:
                        break
                    amt = _q2(min(rec.outstanding_amount, remaining))
                    if amt <= 0:
                        continue
                    register_payroll_loan_deduction(
                        request=request, actor=actor, entry=entry,
                        credit_id=rec.id, amount=amt, credit_type="RECEIVABLE",
                    )
                    abonos.append({"receivable_id": str(rec.obligation_id), "amount": str(amt)})
                    remaining -= amt

                write_event(
                    request=request, module="COMISARIATO",
                    event_type="COMISARIATO_STORE_CREDIT_DEDUCTED", reason_code="COMISARIATO_OK",
                    actor_user=actor, subject_type="COMISARIATO_ACCOUNT", subject_id=str(account.id),
                    metadata={
                        "sheet_id": sheet.id, "entry_id": entry.id, "cedula": ced,
                        "amount": str(due), "abonos": abonos,
                    },
                )
            results.append(
                {"entry_id": entry.id, "account_id": account.id, "amount": str(due), "status": "APPLIED"}
            )
        except Exception as exc:  # noqa: BLE001 — best-effort por entrada
            results.append({"entry_id": entry.id, "status": "ERROR", "error": str(exc)})

    applied = [r for r in results if r["status"] == "APPLIED"]
    total_applied = _q2(sum((Decimal(r["amount"]) for r in applied), Decimal("0.00")))
    return {
        "sheet_id": sheet.id,
        "applied_count": len(applied),
        "total_applied": str(total_applied),
        "results": results,
    }
