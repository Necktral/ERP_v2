from __future__ import annotations

from django.db import models


UNKNOWN_TENDER_PAYMENT_METHOD = ""


class TenderPaymentMethod(models.TextChoices):
    CASH = "CASH", "Cash"
    TRANSFER = "TRANSFER", "Transfer"
    CREDIT = "CREDIT", "Credit"
    CARD = "CARD", "Card"


TENDER_PAYMENT_METHOD_CHOICES = [
    (UNKNOWN_TENDER_PAYMENT_METHOD, "Unknown / historical"),
    *TenderPaymentMethod.choices,
]
TENDER_PAYMENT_METHOD_VALUES = frozenset(value for value, _label in TenderPaymentMethod.choices)
NON_CASH_TENDER_PAYMENT_METHODS = frozenset(
    {
        TenderPaymentMethod.TRANSFER,
        TenderPaymentMethod.CREDIT,
        TenderPaymentMethod.CARD,
    }
)
