"""Pagos del neto de planilla + cierre del período (U5).

Registra el pago del líquido por empleado y mueve el período por su ciclo final:
`APPROVED → PAID` (auto, cuando todas las líneas con neto>0 quedan cubiertas) `→ CLOSED`.
El abono de préstamos a `portfolio` y los endpoints HTTP quedan como follow-up.
"""
from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.modulos.audit.writer import write_event

from .models import PayrollEntry, PayrollPayment, PayrollPeriod, PeriodStatus


class PayrollPaymentError(ValueError):
    """Error de dominio para pagos/cierre de planilla."""


def _entry_is_paid(entry: PayrollEntry) -> bool:
    paid = entry.payments.aggregate(s=Sum("amount"))["s"] or Decimal("0.00")
    return paid >= (entry.net_to_pay or Decimal("0.00"))


def _period_fully_paid(period: PayrollPeriod) -> bool:
    entries = list(PayrollEntry.objects.filter(sheet__period=period).prefetch_related("payments"))
    if not entries:
        return False
    return all(_entry_is_paid(e) for e in entries)


def register_payroll_payment(
    *, request, actor, entry: PayrollEntry, payment_method: str, amount, payment_date=None, reference: str = "", notes: str = ""
) -> PayrollPayment:
    """Registra el pago del neto de una línea. Auto-transiciona el período a PAID si queda cubierto."""
    period = entry.sheet.period
    if period.status not in (PeriodStatus.APPROVED, PeriodStatus.PAID):
        raise PayrollPaymentError(f"El período debe estar APROBADO para pagar (estado: {period.status}).")
    amount = Decimal(str(amount))
    if amount <= 0:
        raise PayrollPaymentError("El monto del pago debe ser > 0.")

    # NM-05: no permitir pagar más que el neto restante (evita sobrepago / pago duplicado).
    already_paid = entry.payments.aggregate(s=Sum("amount"))["s"] or Decimal("0.00")
    remaining = (entry.net_to_pay or Decimal("0.00")) - already_paid
    if amount > remaining:
        raise PayrollPaymentError(
            f"El pago ({amount}) excede el neto restante ({remaining})."
        )

    with transaction.atomic():
        payment = PayrollPayment.objects.create(
            entry=entry,
            company=period.company,
            payment_method=payment_method,
            amount=amount,
            payment_date=payment_date or timezone.now().date(),
            reference=reference or "",
            notes=notes or "",
            created_by=actor,
        )
        write_event(
            request=request,
            module="NOMINA",
            event_type="NOMINA_PAYMENT_REGISTERED",
            reason_code="NOMINA_OK",
            actor_user=actor,
            subject_type="PAYROLL_PAYMENT",
            subject_id=str(payment.id),
            metadata={"period_id": period.id, "entry_id": entry.id, "amount": str(amount), "method": payment_method},
        )
        if period.status == PeriodStatus.APPROVED and _period_fully_paid(period):
            period.status = PeriodStatus.PAID
            period.save(update_fields=["status", "updated_at"])
            write_event(
                request=request,
                module="NOMINA",
                event_type="NOMINA_PERIOD_PAID",
                reason_code="NOMINA_OK",
                actor_user=actor,
                subject_type="PAYROLL_PERIOD",
                subject_id=str(period.id),
                metadata={"period_id": period.id},
            )
        return payment


def close_period(*, request, actor, period: PayrollPeriod) -> PayrollPeriod:
    """Cierra un período PAGADO (PAID → CLOSED)."""
    if period.status != PeriodStatus.PAID:
        raise PayrollPaymentError(f"Solo se puede cerrar un período PAGADO (estado: {period.status}).")
    with transaction.atomic():
        period.status = PeriodStatus.CLOSED
        period.save(update_fields=["status", "updated_at"])
        write_event(
            request=request,
            module="NOMINA",
            event_type="NOMINA_PERIOD_CLOSED",
            reason_code="NOMINA_OK",
            actor_user=actor,
            subject_type="PAYROLL_PERIOD",
            subject_id=str(period.id),
            metadata={"period_id": period.id},
        )
    return period
