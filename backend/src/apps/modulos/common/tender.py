from __future__ import annotations

from django.db import models


UNKNOWN_TENDER_PAYMENT_METHOD = ""


class TenderPaymentMethod(models.TextChoices):
    CASH = "CASH", "Efectivo"
    TRANSFER = "TRANSFER", "Transferencia Bancaria"
    CREDIT = "CREDIT", "Crédito"
    CARD = "CARD", "Tarjeta"
    CHECK = "CHECK", "Cheque"
    PAYROLL_DEDUCTION = "PAYROLL_DEDUCTION", "Descuento de Nómina"
    PRODUCER_CREDIT = "PRODUCER_CREDIT", "Crédito Productor (Café)"
    INTERNAL_TRANSFER = "INTERNAL_TRANSFER", "Traslado Interno"
    COFFEE_QUOTA = "COFFEE_QUOTA", "Cuota de Café (especie)"
    MIXED = "MIXED", "Mixto"


TENDER_PAYMENT_METHOD_CHOICES = [
    (UNKNOWN_TENDER_PAYMENT_METHOD, "Sin especificar"),
    *TenderPaymentMethod.choices,
]
TENDER_PAYMENT_METHOD_VALUES = frozenset(value for value, _label in TenderPaymentMethod.choices)
NON_CASH_TENDER_PAYMENT_METHODS = frozenset(
    {
        TenderPaymentMethod.TRANSFER,
        TenderPaymentMethod.CREDIT,
        TenderPaymentMethod.CARD,
        TenderPaymentMethod.CHECK,
        TenderPaymentMethod.PAYROLL_DEDUCTION,
        TenderPaymentMethod.PRODUCER_CREDIT,
        TenderPaymentMethod.INTERNAL_TRANSFER,
        TenderPaymentMethod.COFFEE_QUOTA,
    }
)
