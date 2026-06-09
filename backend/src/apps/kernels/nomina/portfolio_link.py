"""Puente nómina → portfolio: abono de descuentos de préstamo/adelanto de planilla.

Registra el `PayrollLoanDeduction` (link auditado entre la línea de planilla y el crédito
del empleado en `portfolio`) y aplica el abono al saldo del crédito (best-effort: nunca
bloquea la nómina). El abono usa `portfolio.apply_payroll_abono` (sin payment intent).
"""
from __future__ import annotations

import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.modulos.audit.writer import write_event

from .models import PayrollLoanDeduction

logger = logging.getLogger(__name__)


def _apply_to_portfolio(*, deduction: PayrollLoanDeduction, amount: Decimal, actor, abono_date):
    """Aplica el abono al crédito/CxC del empleado en portfolio (best-effort)."""
    try:
        from apps.kernels.portfolio.models import Credit, Receivable
        from apps.kernels.portfolio.services import PortfolioDomainError, apply_payroll_abono
    except ImportError:
        return None

    model = Receivable if deduction.credit_type == "RECEIVABLE" else Credit
    obligation = model.objects.filter(id=deduction.credit_id).first()
    if obligation is None:
        return None
    try:
        return apply_payroll_abono(
            obligation=obligation,
            amount=amount,
            abono_date=abono_date,
            created_by=actor,
            reference=f"PLANILLA:deduction:{deduction.id}",
        )
    except (PortfolioDomainError, ValueError, RuntimeError, TypeError):
        return None


def register_payroll_loan_deduction(
    *, request, actor, entry, credit_id, amount, credit_type: str = "CREDIT", abono_date=None
):
    """Registra el descuento de préstamo de una línea y abona al crédito en portfolio (best-effort).

    Devuelve (PayrollLoanDeduction, monto_abonado | None).
    """
    amount = Decimal(str(amount))
    period = entry.sheet.period
    with transaction.atomic():
        deduction = PayrollLoanDeduction.objects.create(
            entry=entry,
            company=period.company,
            credit_id=int(credit_id),
            credit_type=(credit_type or "CREDIT").upper(),
            amount_deducted=amount,
        )
        write_event(
            request=request,
            module="NOMINA",
            event_type="NOMINA_LOAN_DEDUCTION_RECORDED",
            reason_code="NOMINA_OK",
            actor_user=actor,
            subject_type="PAYROLL_LOAN_DEDUCTION",
            subject_id=str(deduction.id),
            metadata={
                "entry_id": entry.id,
                "credit_id": int(credit_id),
                "credit_type": deduction.credit_type,
                "amount": str(amount),
            },
        )

    # Best-effort, fuera de la txn del registro: la nómina nunca se bloquea por portfolio.
    applied = _apply_to_portfolio(
        deduction=deduction, amount=amount, actor=actor, abono_date=abono_date or timezone.localdate()
    )

    # NM-06: registrar lo realmente abonado. Si falla (applied None) o queda corto, la
    # deducción queda con `abono_applied` < `amount_deducted` → abono pendiente, visible
    # para conciliación (antes el trabajador quedaba descontado sin abonar el crédito y
    # el desfase era silencioso).
    deduction.abono_applied = applied if applied is not None else Decimal("0.00")
    deduction.save(update_fields=["abono_applied"])
    if deduction.abono_applied < amount:
        logger.warning(
            "payroll_loan_abono_pending",
            extra={
                "deduction_id": deduction.id,
                "credit_id": int(credit_id),
                "credit_type": deduction.credit_type,
                "amount_deducted": str(amount),
                "abono_applied": str(deduction.abono_applied),
            },
        )
    return deduction, applied
