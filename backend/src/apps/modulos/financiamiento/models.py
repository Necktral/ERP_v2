"""Modelos del módulo FINANCIAMIENTO (reemplazo del SIFA-ACOPIO VB6).

Vertical que orquesta los kernels — NO duplica motores: el saldo del préstamo vive
en ``portfolio.Credit`` (uno por moneda: doble saldo C$/US$ fiel al SIFA), los abonos
en ``payments``+``portfolio.PaymentAllocation``, y el café físico en ``inventarios``
(bodega de CUSTODIA: el café entregado sigue siendo del productor hasta la fijación
de precio; la liquidación lo compra y abona el préstamo en un solo acto).

Lo genuinamente nuevo del vertical: el perfil de productor (código de acopio,
certificaciones), la solicitud con garantías (fiel al SIFA: finca/solar/otras/café-QQ),
el préstamo dual-moneda como agregado, la recepción de acopio con clasificación/tara,
la fijación de precio y la liquidación con retenciones.
"""
from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.modulos.iam.models import OrgUnit


class Currency(models.TextChoices):
    NIO = "NIO", "Córdoba"
    USD = "USD", "Dólar"


class ProducerProfile(models.Model):
    """Productor/cooperativa sujeto de financiamiento (el SIFA lo llamaba `Cooperativas`).

    La identidad vive en ``parties.Party`` (cédula = ``national_id``); aquí solo lo
    propio del vertical: código de acopio y certificaciones (UTZ, etc.).
    """

    company = models.ForeignKey(
        OrgUnit, on_delete=models.PROTECT, related_name="financing_producers",
        help_text="Empresa financiadora (acopiadora).",
    )
    party = models.ForeignKey(
        "parties.Party", on_delete=models.PROTECT, related_name="financing_producer_profiles",
    )
    acopio_code = models.CharField(
        max_length=32, blank=True, default="",
        help_text="Código de acopio del productor (numeración histórica del SIFA).",
    )
    certifications = models.CharField(
        max_length=255, blank=True, default="",
        help_text="Certificaciones del productor (UTZ, orgánico, etc.).",
    )
    is_active = models.BooleanField(default=True)
    notes = models.CharField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "financiamiento"
        constraints = [
            models.UniqueConstraint(fields=["company", "party"], name="uq_fin_producer_party"),
            models.UniqueConstraint(
                fields=["company", "acopio_code"],
                condition=~models.Q(acopio_code=""),
                name="uq_fin_producer_acopio_code",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.acopio_code or self.pk} {self.party.display_name}"


class ApplicationStatus(models.TextChoices):
    DRAFT = "DRAFT", "Borrador"
    SUBMITTED = "SUBMITTED", "Presentada"
    APPROVED = "APPROVED", "Aprobada"
    REJECTED = "REJECTED", "Rechazada"
    DISBURSED = "DISBURSED", "Desembolsada"


class DisbursementForm(models.TextChoices):
    CASH = "CASH", "Efectivo"
    CHECK = "CHECK", "Cheque"
    TRANSFER = "TRANSFER", "Transferencia"
    IN_KIND = "IN_KIND", "Especie (insumos)"


class CreditApplication(models.Model):
    """Solicitud de crédito del productor (tabla `Solicitud` del SIFA), con las
    garantías estructuradas tal cual las pedía el programa viejo."""

    company = models.ForeignKey(
        OrgUnit, on_delete=models.PROTECT, related_name="financing_applications",
    )
    producer = models.ForeignKey(
        ProducerProfile, on_delete=models.PROTECT, related_name="applications",
    )
    requested_nio = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0.00"),
        help_text="Monto solicitado en córdobas (puede ser 0 si solo pide dólares).",
    )
    requested_usd = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0.00"),
        help_text="Monto solicitado en dólares (puede ser 0 si solo pide córdobas).",
    )
    term_months = models.PositiveIntegerField(help_text="Plazo en meses.")
    credit_type = models.CharField(
        max_length=32, blank=True, default="",
        help_text="Tipo de crédito (catálogo libre del SIFA: avío, comercial, etc.).",
    )
    activity = models.CharField(
        max_length=64, blank=True, default="",
        help_text="Actividad financiada (mantenimiento de café, recolección, etc.).",
    )
    interest_rate = models.DecimalField(
        max_digits=7, decimal_places=4, help_text="Interés corriente anual (%).",
    )
    penalty_rate = models.DecimalField(
        max_digits=7, decimal_places=4, default=Decimal("0.0000"),
        help_text="Interés moratorio anual (%).",
    )
    commission_rate = models.DecimalField(
        max_digits=7, decimal_places=4, default=Decimal("0.0000"),
        help_text="Comisión sobre el monto desembolsado (%).",
    )
    disbursement_form = models.CharField(
        max_length=16, choices=DisbursementForm.choices, default=DisbursementForm.CASH,
    )
    # Garantías (fiel al SIFA: GarantiaInmovFincArea / Solar / Otras / MovCafeQQ).
    guarantee_farm_area_mz = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"),
        help_text="Garantía inmueble: área de finca (manzanas).",
    )
    guarantee_solar = models.CharField(
        max_length=255, blank=True, default="", help_text="Garantía inmueble: solar.",
    )
    guarantee_other = models.CharField(
        max_length=255, blank=True, default="", help_text="Otras garantías.",
    )
    guarantee_coffee_qq = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"),
        help_text="Garantía mueble: café comprometido (quintales).",
    )
    status = models.CharField(
        max_length=16, choices=ApplicationStatus.choices, default=ApplicationStatus.DRAFT,
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="financing_applications_decided",
    )
    rejection_reason = models.CharField(max_length=500, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="financing_applications_created",
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "financiamiento"
        indexes = [models.Index(fields=["company", "status"])]

    def __str__(self) -> str:
        return f"Solicitud #{self.pk} {self.producer} ({self.status})"


class LoanStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Activo"
    PAID = "PAID", "Cancelado (pagado)"
    CANCELLED = "CANCELLED", "Anulado"


class FinancingLoan(models.Model):
    """Préstamo del productor con DOBLE SALDO (C$ y US$) fiel al SIFA.

    El agregado envuelve 1-2 ``portfolio.Credit`` — uno por moneda con monto > 0 —
    para que cada saldo viva en SU moneda (allocations limpias, devengo del kernel).
    El estado de cuenta consolida ambos con la tasa vigente (``ExchangeRate``).
    """

    company = models.ForeignKey(
        OrgUnit, on_delete=models.PROTECT, related_name="financing_loans",
    )
    producer = models.ForeignKey(
        ProducerProfile, on_delete=models.PROTECT, related_name="loans",
    )
    application = models.OneToOneField(
        CreditApplication, on_delete=models.PROTECT, null=True, blank=True, related_name="loan",
    )
    reference = models.CharField(
        max_length=40, help_text="Número de préstamo (referencia del SIFA).",
    )
    credit_type = models.CharField(max_length=32, blank=True, default="")
    activity = models.CharField(max_length=64, blank=True, default="")
    interest_rate = models.DecimalField(max_digits=7, decimal_places=4)
    penalty_rate = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("0.0000"))
    commission_rate = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("0.0000"))
    term_months = models.PositiveIntegerField()
    maturity_date = models.DateField()
    disbursement_form = models.CharField(
        max_length=16, choices=DisbursementForm.choices, default=DisbursementForm.CASH,
    )
    disbursed_at = models.DateField(null=True, blank=True)
    credit_nio = models.OneToOneField(
        "portfolio.Credit", on_delete=models.PROTECT, null=True, blank=True,
        related_name="financing_loan_nio", help_text="Obligación del saldo en córdobas.",
    )
    credit_usd = models.OneToOneField(
        "portfolio.Credit", on_delete=models.PROTECT, null=True, blank=True,
        related_name="financing_loan_usd", help_text="Obligación del saldo en dólares.",
    )
    status = models.CharField(max_length=16, choices=LoanStatus.choices, default=LoanStatus.ACTIVE)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="financing_loans_created",
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "financiamiento"
        constraints = [
            models.UniqueConstraint(fields=["company", "reference"], name="uq_fin_loan_reference"),
        ]
        indexes = [models.Index(fields=["company", "status"])]

    def __str__(self) -> str:
        return f"Préstamo {self.reference} ({self.producer})"

    def credit_for(self, currency: str):
        return self.credit_nio if currency == Currency.NIO else self.credit_usd


class ExchangeRate(models.Model):
    """Tasa de cambio C$ por 1 US$ vigente por fecha (precedente:
    ``nomina.PayrollPeriod.exchange_rate_usd``). Fuente para consolidar el doble saldo."""

    company = models.ForeignKey(
        OrgUnit, on_delete=models.PROTECT, related_name="financing_exchange_rates",
    )
    rate_date = models.DateField()
    rate = models.DecimalField(
        max_digits=12, decimal_places=6, help_text="Córdobas por 1 dólar.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="financing_rates_created",
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        app_label = "financiamiento"
        constraints = [
            models.UniqueConstraint(fields=["company", "rate_date"], name="uq_fin_rate_date"),
        ]
        indexes = [models.Index(fields=["company", "-rate_date"])]

    def __str__(self) -> str:
        return f"{self.rate_date}: {self.rate} C$/US$"


class CoffeeQualityGrade(models.Model):
    """Catálogo de clasificación/calidad del café acopiado (tabla `Clasificacion`)."""

    company = models.ForeignKey(
        OrgUnit, on_delete=models.PROTECT, related_name="financing_quality_grades",
    )
    code = models.CharField(max_length=16)
    name = models.CharField(max_length=80)
    default_tare_pct = models.DecimalField(
        max_digits=6, decimal_places=2, default=Decimal("0.00"),
        help_text="Tara sugerida por calidad (% del peso bruto; el SIFA: TaraCalidad).",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        app_label = "financiamiento"
        constraints = [
            models.UniqueConstraint(fields=["company", "code"], name="uq_fin_quality_code"),
        ]

    def __str__(self) -> str:
        return f"{self.code} {self.name}"


class PhysicalState(models.TextChoices):
    WET = "MOJADO", "Mojado"
    HUMID = "HUMEDO", "Húmedo"
    AIRED = "OREADO", "Oreado"
    DRY = "SECO", "Pergamino seco"


class CoffeeReception(models.Model):
    """Recepción de café del productor EN CUSTODIA (tabla `Acopiado2` del SIFA).

    El café entra a la bodega de custodia vía ``inventarios.post_receive`` (costo 0:
    aún no es nuestro); el peso neto alimenta el depósito del productor hasta que
    una fijación de precio lo comprometa y una liquidación lo compre.
    """

    company = models.ForeignKey(
        OrgUnit, on_delete=models.PROTECT, related_name="financing_receptions",
    )
    producer = models.ForeignKey(
        ProducerProfile, on_delete=models.PROTECT, related_name="receptions",
    )
    warehouse = models.ForeignKey(
        "inventarios.Warehouse", on_delete=models.PROTECT, related_name="financing_receptions",
    )
    reception_date = models.DateField()
    reference = models.CharField(
        max_length=40, blank=True, default="", help_text="Número de recibo de café.",
    )
    quality = models.ForeignKey(
        CoffeeQualityGrade, on_delete=models.PROTECT, related_name="receptions",
    )
    physical_state = models.CharField(
        max_length=16, choices=PhysicalState.choices, default=PhysicalState.HUMID,
    )
    sacks = models.PositiveIntegerField(help_text="Número de sacos.")
    gross_lb = models.DecimalField(max_digits=14, decimal_places=2, help_text="Libras brutas.")
    tare_lb = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00"),
        help_text="Tara en libras (por calidad/sacos).",
    )
    net_lb = models.DecimalField(max_digits=14, decimal_places=2, help_text="Libras netas.")
    stock_movement_id = models.PositiveIntegerField(
        null=True, blank=True, help_text="Movimiento RECEIVE en custodia (trazabilidad).",
    )
    note = models.CharField(max_length=300, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="financing_receptions_created",
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        app_label = "financiamiento"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "reference"],
                condition=~models.Q(reference=""),
                name="uq_fin_reception_reference",
            ),
        ]
        indexes = [models.Index(fields=["company", "producer", "reception_date"])]

    def __str__(self) -> str:
        return f"Recepción {self.reference or self.pk}: {self.net_lb} lb ({self.producer})"


class FixationStatus(models.TextChoices):
    OPEN = "OPEN", "Fijada (sin liquidar)"
    LIQUIDATED = "LIQUIDATED", "Liquidada"


class PriceFixation(models.Model):
    """Fijación de precio sobre el depósito del productor (reporte `Fijacion` del SIFA).

    El productor decide CUÁNDO fijar precio para X libras de su depósito; la fijación
    compromete esas libras (salen del disponible) hasta que la liquidación las compre.
    """

    company = models.ForeignKey(
        OrgUnit, on_delete=models.PROTECT, related_name="financing_fixations",
    )
    producer = models.ForeignKey(
        ProducerProfile, on_delete=models.PROTECT, related_name="fixations",
    )
    fixation_date = models.DateField()
    pounds = models.DecimalField(max_digits=14, decimal_places=2, help_text="Libras fijadas.")
    price_per_lb = models.DecimalField(
        max_digits=12, decimal_places=4, help_text="Precio por libra (Valorflib del SIFA).",
    )
    currency = models.CharField(max_length=8, choices=Currency.choices, default=Currency.USD)
    status = models.CharField(
        max_length=16, choices=FixationStatus.choices, default=FixationStatus.OPEN,
    )
    liquidation = models.ForeignKey(
        "financiamiento.Liquidation", on_delete=models.PROTECT, null=True, blank=True,
        related_name="fixations",
    )
    note = models.CharField(max_length=300, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="financing_fixations_created",
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        app_label = "financiamiento"
        indexes = [models.Index(fields=["company", "producer", "status"])]

    def __str__(self) -> str:
        return f"Fijación #{self.pk}: {self.pounds} lb @ {self.price_per_lb} {self.currency}"


class Liquidation(models.Model):
    """Liquidación (F8 del SIFA): compra el café fijado y abona el préstamo en un acto.

    valor bruto (Σ libras×precio) − retenciones → abono al ``Credit`` de la moneda
    (vía PaymentIntent COFFEE_QUOTA + allocation del kernel) → excedente a favor del
    productor como ``portfolio.Payable``. El café sale de custodia y entra al
    inventario propio con costo = valor de compra.
    """

    company = models.ForeignKey(
        OrgUnit, on_delete=models.PROTECT, related_name="financing_liquidations",
    )
    producer = models.ForeignKey(
        ProducerProfile, on_delete=models.PROTECT, related_name="liquidations",
    )
    loan = models.ForeignKey(
        FinancingLoan, on_delete=models.PROTECT, null=True, blank=True,
        related_name="liquidations",
        help_text="Préstamo abonado; NULL = liquidación sin deuda (todo excedente).",
    )
    liquidation_date = models.DateField()
    currency = models.CharField(max_length=8, choices=Currency.choices)
    pounds_total = models.DecimalField(max_digits=14, decimal_places=2)
    gross_value = models.DecimalField(max_digits=18, decimal_places=2)
    deductions_total = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0.00"),
    )
    applied_to_loan = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0.00"),
        help_text="Monto abonado al préstamo (en la moneda de la obligación abonada).",
    )
    applied_currency = models.CharField(
        max_length=8, choices=Currency.choices, blank=True, default="",
        help_text="Moneda de la obligación abonada (puede diferir si cruzó con tasa).",
    )
    surplus_amount = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0.00"),
        help_text="Excedente a favor del productor (CxP).",
    )
    exchange_rate_used = models.DecimalField(
        max_digits=12, decimal_places=6, null=True, blank=True,
    )
    payment_intent_id = models.UUIDField(null=True, blank=True)
    payable = models.ForeignKey(
        "portfolio.Payable", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="financing_liquidations",
    )
    custody_issue_movement_id = models.PositiveIntegerField(null=True, blank=True)
    own_receive_movement_id = models.PositiveIntegerField(null=True, blank=True)
    note = models.CharField(max_length=300, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="financing_liquidations_created",
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        app_label = "financiamiento"
        indexes = [models.Index(fields=["company", "producer", "liquidation_date"])]

    def __str__(self) -> str:
        return f"Liquidación #{self.pk}: {self.gross_value} {self.currency} ({self.producer})"


class LiquidationDeduction(models.Model):
    """Retención/deducción aplicada en la liquidación (tabla `AretencionEmp` del SIFA)."""

    liquidation = models.ForeignKey(
        Liquidation, on_delete=models.CASCADE, related_name="deductions",
    )
    concept = models.CharField(max_length=120)
    amount = models.DecimalField(max_digits=18, decimal_places=2)

    class Meta:
        app_label = "financiamiento"

    def __str__(self) -> str:
        return f"{self.concept}: {self.amount}"


class FinancingSettings(models.Model):
    """Configuración del vertical por empresa: quién presta y dónde vive el café."""

    company = models.OneToOneField(
        OrgUnit, on_delete=models.PROTECT, related_name="financing_settings",
    )
    lender_party = models.ForeignKey(
        "parties.Party", on_delete=models.PROTECT, related_name="financing_lender_settings",
        help_text="Party INTERNAL que representa a la empresa como acreedora.",
    )
    coffee_item = models.ForeignKey(
        "inventarios.InventoryItem", on_delete=models.PROTECT, null=True, blank=True,
        related_name="financing_settings",
        help_text="Ítem de inventario que representa el café acopiado (UoM libra).",
    )
    custody_warehouse = models.ForeignKey(
        "inventarios.Warehouse", on_delete=models.PROTECT, null=True, blank=True,
        related_name="financing_custody_settings",
        help_text="Bodega de CUSTODIA (café del productor sin liquidar).",
    )
    liquidation_warehouse = models.ForeignKey(
        "inventarios.Warehouse", on_delete=models.PROTECT, null=True, blank=True,
        related_name="financing_own_settings",
        help_text="Bodega propia a la que entra el café comprado al liquidar.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "financiamiento"

    def __str__(self) -> str:
        return f"Config financiamiento de {self.company}"
