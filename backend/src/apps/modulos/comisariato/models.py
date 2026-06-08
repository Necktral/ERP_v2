"""Modelos del comisariato (tienda de la empresa que vende a crédito).

El comisariato es una empresa con RUC propio que vende a crédito a 3 segmentos
de cliente (trabajadores de la hacienda, productores, público general), cada uno
con un límite de crédito. La VENTA no tiene modelo propio: es un ``BillingDocument``
de facturacion (factura a crédito de inventario). Lo único genuinamente nuevo es la
cuenta de crédito por cliente, que vive aquí.
"""
from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.modulos.iam.models import OrgUnit


class CustomerSegment(models.TextChoices):
    EMPLOYEE = "EMPLOYEE", "Trabajador de la hacienda"
    PRODUCER = "PRODUCER", "Productor"
    PUBLIC = "PUBLIC", "Público general"


class CustomerCreditAccount(models.Model):
    """Cuenta de crédito de un cliente del comisariato (límite + segmento).

    El saldo NO se guarda aquí: vive en portfolio (CxC del party). El crédito
    disponible se calcula como ``credit_limit − Σ CxC abierta`` del party en la
    empresa del comisariato. ``credit_limit == 0`` significa "sin tope explícito".
    """

    company = models.ForeignKey(
        OrgUnit, on_delete=models.PROTECT, related_name="comisariato_credit_accounts",
        help_text="Empresa del comisariato (RUC propio) que otorga el crédito.",
    )
    party = models.ForeignKey(
        "parties.Party", on_delete=models.PROTECT, related_name="comisariato_credit_accounts",
        help_text="Cliente (trabajador / productor / público).",
    )
    segment = models.CharField(max_length=16, choices=CustomerSegment.choices)
    credit_limit = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0.00"),
        help_text="Límite de crédito; 0 = sin tope explícito.",
    )
    collecting_company = models.ForeignKey(
        OrgUnit, on_delete=models.PROTECT, null=True, blank=True,
        related_name="comisariato_collected_accounts",
        help_text="Para EMPLOYEE: la finca/empresa que descuenta en planilla (cobra por cuenta del comisariato).",
    )
    is_active = models.BooleanField(default=True)
    notes = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "comisariato"
        constraints = [
            models.UniqueConstraint(fields=["company", "party"], name="uq_comisariato_account_company_party"),
            models.CheckConstraint(
                condition=models.Q(credit_limit__gte=0), name="ck_comisariato_account_limit_nonneg"
            ),
        ]
        indexes = [
            models.Index(fields=["company", "is_active", "segment"], name="ix_comis_acct_co_act_seg"),
            models.Index(fields=["party"], name="ix_comis_acct_party"),
        ]

    def clean(self):
        super().clean()
        if self.company_id and self.company.unit_type != OrgUnit.UnitType.COMPANY:
            raise ValidationError({"company": "company debe ser OrgUnit de tipo COMPANY."})
        if self.party_id and self.company_id and self.party.company_id != self.company_id:
            raise ValidationError({"party": "party debe pertenecer a la empresa del comisariato."})
        if self.credit_limit < 0:
            raise ValidationError({"credit_limit": "credit_limit no puede ser negativo."})

    def __str__(self) -> str:
        return f"ComisariatoAccount<{self.company_id}:{self.party_id}:{self.segment}>"
