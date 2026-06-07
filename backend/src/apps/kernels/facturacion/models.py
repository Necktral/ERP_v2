from __future__ import annotations

import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.modulos.common.tender import TENDER_PAYMENT_METHOD_CHOICES


# ---------------------------------------------------------------------------
# Choices globales
# ---------------------------------------------------------------------------

class DocType(models.TextChoices):
    INVOICE = "INVOICE", "Factura"
    CREDIT_NOTE = "CREDIT_NOTE", "Nota de Crédito"
    QUOTE = "QUOTE", "Cotización / Proforma"
    ORDER = "ORDER", "Orden de Venta (por encargo)"


class DocStatus(models.TextChoices):
    DRAFT = "DRAFT", "Borrador"
    ISSUED = "ISSUED", "Emitida"
    VOIDED = "VOIDED", "Anulada"


class PaymentStatus(models.TextChoices):
    UNPAID = "UNPAID", "Sin pagar"
    PARTIAL = "PARTIAL", "Pago parcial"
    PAID = "PAID", "Pagada"
    OVERPAID = "OVERPAID", "Sobrepago"


class CustomerType(models.TextChoices):
    WORKER = "WORKER", "Trabajador de la empresa"
    PRODUCER_FINANCED = "PRODUCER_FINANCED", "Productor en financiamiento"
    EXTERNAL = "EXTERNAL", "Cliente externo"
    INTERNAL = "INTERNAL", "Traslado interno"


class CreditStatus(models.TextChoices):
    NONE = "NONE", "No requiere crédito"
    PENDING_REVIEW = "PENDING_REVIEW", "Pendiente de revisión"
    IN_REVIEW = "IN_REVIEW", "En revisión"
    APPROVED = "APPROVED", "Aprobado"
    REJECTED = "REJECTED", "Rechazado"
    ESCALATED = "ESCALATED", "Escalado a gerencia"


class FiscalMode(models.TextChoices):
    NOOP = "NOOP", "Sin fiscal"
    A = "A", "Adapter A"
    B = "B", "Adapter B"


class FiscalStatus(models.TextChoices):
    NUMBER_RESERVED = "NUMBER_RESERVED", "Número reservado"
    ISSUED = "ISSUED", "Emitida"
    PRINTED = "PRINTED", "Impresa"
    FAILED_PRINT = "FAILED_PRINT", "Error de impresión"
    CONTINGENCY = "CONTINGENCY", "Contingencia"
    VOIDED = "VOIDED", "Anulada"


# ---------------------------------------------------------------------------
# SalesOrder — por encargo
# ---------------------------------------------------------------------------

class SalesOrderStatus(models.TextChoices):
    DRAFT = "DRAFT", "Borrador"
    PENDING_APPROVAL = "PENDING_APPROVAL", "Pendiente de aprobación"
    IN_REVIEW = "IN_REVIEW", "En revisión"
    APPROVED = "APPROVED", "Aprobado"
    REJECTED = "REJECTED", "Rechazado"
    PURCHASE_ORDERED = "PURCHASE_ORDERED", "Orden de compra emitida"
    PURCHASE_RECEIVED = "PURCHASE_RECEIVED", "Mercancía recibida"
    READY = "READY", "Listo para despachar"
    FULFILLED = "FULFILLED", "Despachado y facturado"
    CANCELLED = "CANCELLED", "Cancelado"


class SalesOrder(models.Model):
    order_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)

    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="sales_orders_company")
    branch = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="sales_orders_branch")

    status = models.CharField(max_length=24, choices=SalesOrderStatus.choices, default=SalesOrderStatus.DRAFT, db_index=True)
    customer_type = models.CharField(max_length=24, choices=CustomerType.choices, default=CustomerType.EXTERNAL)
    customer_party = models.ForeignKey(
        "parties.Party", null=True, blank=True, on_delete=models.PROTECT, related_name="sales_orders"
    )
    customer_name = models.CharField(max_length=160, blank=True, default="")
    customer_ref = models.CharField(max_length=64, blank=True, default="")

    currency = models.CharField(max_length=8, default="NIO")
    subtotal = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    tax_total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    discount_total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

    expected_delivery_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")

    credit_status = models.CharField(max_length=16, choices=CreditStatus.choices, default=CreditStatus.NONE, db_index=True)
    credit_notes = models.TextField(blank=True, default="")
    credit_approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="sales_orders_credit_approved"
    )
    credit_approved_at = models.DateTimeField(null=True, blank=True)

    purchase_order_ref = models.CharField(max_length=96, blank=True, default="")
    billing_doc = models.ForeignKey(
        "facturacion.BillingDocument", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="from_sales_orders"
    )

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="sales_orders_requested"
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="sales_orders_reviewed"
    )

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "facturacion"
        indexes = [
            models.Index(fields=["company", "status", "created_at"], name="ix_so_c_st_ca"),
            models.Index(fields=["company", "customer_party", "status"], name="ix_so_c_cp_st"),
            models.Index(fields=["company", "credit_status"], name="ix_so_c_crs"),
        ]

    def __str__(self) -> str:
        return f"Orden {self.order_id} [{self.status}]"


class SalesOrderLine(models.Model):
    order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey(
        "inventarios.InventoryItem", null=True, blank=True,
        on_delete=models.PROTECT, related_name="sales_order_lines"
    )
    description = models.CharField(max_length=200)
    quantity = models.DecimalField(max_digits=18, decimal_places=4)
    unit_price = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal("0.000000"))
    tax_rate = models.DecimalField(max_digits=8, decimal_places=4, default=Decimal("0.0000"))
    discount_pct = models.DecimalField(max_digits=6, decimal_places=4, default=Decimal("0.0000"))

    line_subtotal = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    line_tax = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    line_total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

    preferred_warehouse = models.ForeignKey(
        "inventarios.Warehouse", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="sales_order_lines"
    )
    qty_available_snapshot = models.DecimalField(
        max_digits=18, decimal_places=4, default=Decimal("0.0000"),
        help_text="Stock disponible al crear la orden"
    )
    notes = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        app_label = "facturacion"


# ---------------------------------------------------------------------------
# CreditApprovalRequest
# ---------------------------------------------------------------------------

class CreditApprovalRequest(models.Model):
    class ApprovalStatus(models.TextChoices):
        PENDING = "PENDING", "Pendiente"
        IN_REVIEW = "IN_REVIEW", "En revisión"
        APPROVED = "APPROVED", "Aprobado"
        REJECTED = "REJECTED", "Rechazado"
        ESCALATED = "ESCALATED", "Escalado"
        CANCELLED = "CANCELLED", "Cancelado"

    class ApprovalLevel(models.TextChoices):
        SALES_MANAGER = "SALES_MANAGER", "Gerente de Ventas"
        CREDIT_COMMITTEE = "CREDIT_COMMITTEE", "Comité de Crédito"
        CEO = "CEO", "Gerencia General"

    request_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="credit_approvals_company")

    sales_order = models.ForeignKey(
        SalesOrder, null=True, blank=True, on_delete=models.CASCADE, related_name="credit_approvals"
    )
    billing_doc = models.ForeignKey(
        "facturacion.BillingDocument", null=True, blank=True,
        on_delete=models.CASCADE, related_name="credit_approvals"
    )

    status = models.CharField(max_length=16, choices=ApprovalStatus.choices, default=ApprovalStatus.PENDING, db_index=True)
    level = models.CharField(max_length=24, choices=ApprovalLevel.choices, default=ApprovalLevel.SALES_MANAGER, db_index=True)

    amount_requested = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    currency = models.CharField(max_length=8, default="NIO")

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="credit_requests_made"
    )
    requested_at = models.DateTimeField(default=timezone.now, editable=False)
    request_notes = models.TextField(blank=True, default="")

    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="credit_requests_assigned"
    )
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="credit_requests_resolved"
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(blank=True, default="")

    approved_amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    approved_terms_days = models.PositiveIntegerField(null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "facturacion"
        indexes = [
            models.Index(fields=["company", "status", "level"], name="ix_cra_c_st_lv"),
            models.Index(fields=["assigned_to", "status"], name="ix_cra_at_st"),
            models.Index(fields=["company", "requested_at"], name="ix_cra_c_ra"),
        ]

    def __str__(self) -> str:
        return f"CreditRequest {self.request_id} [{self.status}]"


# ---------------------------------------------------------------------------
# BillingSequence
# ---------------------------------------------------------------------------

class BillingSequence(models.Model):
    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="bill_seq_company")
    branch = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="bill_seq_branch")
    doc_type = models.CharField(max_length=16, choices=DocType.choices)
    series = models.CharField(max_length=16, default="A")
    next_number = models.IntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "facturacion"
        constraints = [
            models.UniqueConstraint(fields=["company", "branch", "doc_type", "series"], name="uniq_bill_seq"),
        ]


# ---------------------------------------------------------------------------
# BillingDocument
# ---------------------------------------------------------------------------

class BillingDocument(models.Model):
    class AccountingStatus(models.TextChoices):
        DISABLED = "DISABLED", "Disabled"
        UNSUPPORTED = "UNSUPPORTED", "Unsupported"
        PENDING_RULESET = "PENDING_RULESET", "Pending ruleset"
        PENDING_RULE = "PENDING_RULE", "Pending rule"
        DRAFT_EXCEPTION = "DRAFT_EXCEPTION", "Draft exception"
        DRAFT_VALIDATED = "DRAFT_VALIDATED", "Draft validated"
        POSTED = "POSTED", "Posted"

    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="bill_docs_company")
    branch = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="bill_docs_branch")

    doc_type = models.CharField(max_length=16, choices=DocType.choices)
    status = models.CharField(max_length=16, choices=DocStatus.choices, default=DocStatus.DRAFT, db_index=True)

    series = models.CharField(max_length=16, default="A")
    number = models.IntegerField(default=0)

    currency = models.CharField(max_length=8, default="NIO")
    customer_name = models.CharField(max_length=160, blank=True, default="")
    customer_ref = models.CharField(max_length=64, blank=True, default="")
    customer_party = models.ForeignKey(
        "parties.Party", null=True, blank=True,
        on_delete=models.PROTECT, related_name="billing_documents",
    )
    customer_type = models.CharField(
        max_length=24, choices=CustomerType.choices, default=CustomerType.EXTERNAL, db_index=True
    )

    subtotal = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    discount_total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    tax_total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

    # Pagos
    payment_method = models.CharField(max_length=24, choices=TENDER_PAYMENT_METHOD_CHOICES, blank=True, default="")
    payment_status = models.CharField(
        max_length=12, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID, db_index=True
    )
    amount_paid = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

    # Crédito
    credit_status = models.CharField(
        max_length=16, choices=CreditStatus.choices, default=CreditStatus.NONE, db_index=True
    )
    credit_notes = models.TextField(blank=True, default="")
    credit_approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="bill_docs_credit_approved"
    )
    credit_approved_at = models.DateTimeField(null=True, blank=True)

    # Fiscal
    is_fiscal = models.BooleanField(default=False)
    fiscal_mode_resolved = models.CharField(max_length=8, choices=FiscalMode.choices, default=FiscalMode.NOOP)
    fiscal_status = models.CharField(max_length=24, choices=FiscalStatus.choices, blank=True, default="")
    fiscal_reference = models.CharField(max_length=96, blank=True, default="")
    fiscal_evidence_id = models.CharField(max_length=96, blank=True, default="")
    print_attempt_count = models.PositiveIntegerField(default=0)
    last_print_error = models.CharField(max_length=255, blank=True, default="")
    contingency_reason = models.CharField(max_length=255, blank=True, default="")
    contingency_at = models.DateTimeField(null=True, blank=True)
    printed_at = models.DateTimeField(null=True, blank=True)
    fiscal_metadata_json = models.JSONField(default=dict)

    idempotency_key = models.CharField(max_length=96, blank=True, default="")
    source_module = models.CharField(max_length=32, blank=True, default="")
    source_type = models.CharField(max_length=64, blank=True, default="")
    source_id = models.CharField(max_length=64, blank=True, default="")

    # Nota de crédito: enlace al documento original y monto ya acreditado del original.
    related_doc = models.ForeignKey(
        "facturacion.BillingDocument",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="credit_notes_of",
    )
    credited_total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

    issued_at = models.DateTimeField(null=True, blank=True)
    voided_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.CharField(max_length=255, blank=True, default="")

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="bill_docs_created"
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    accounting_status = models.CharField(
        max_length=24, choices=AccountingStatus.choices, blank=True, default=""
    )
    accounting_error = models.CharField(max_length=255, blank=True, default="")
    accounting_economic_event = models.ForeignKey(
        "accounting.EconomicEvent", null=True, blank=True,
        on_delete=models.PROTECT, related_name="billing_documents",
    )
    accounting_journal_draft = models.ForeignKey(
        "accounting.JournalDraft", null=True, blank=True,
        on_delete=models.PROTECT, related_name="billing_documents",
    )
    accounting_journal_entry = models.ForeignKey(
        "accounting.JournalEntry", null=True, blank=True,
        on_delete=models.PROTECT, related_name="billing_documents",
    )

    class Meta:
        app_label = "facturacion"
        indexes = [
            models.Index(fields=["company", "branch", "created_at"], name="ix_billdoc_c_b_ca"),
            models.Index(fields=["company", "branch", "doc_type", "status", "created_at"], name="ix_billdoc_c_b_t_s_ca"),
            models.Index(fields=["company", "idempotency_key"], name="ix_billdoc_c_idem"),
            models.Index(fields=["company", "customer_party"], name="ix_billdoc_co_cust_party"),
            models.Index(fields=["company", "branch", "fiscal_mode_resolved", "fiscal_status"], name="ix_billdoc_fiscal"),
            models.Index(fields=["company", "branch", "accounting_status", "created_at"], name="ix_billdoc_acc_st"),
            models.Index(fields=["company", "payment_status", "created_at"], name="ix_billdoc_pay_st"),
            models.Index(fields=["company", "credit_status"], name="ix_billdoc_crs"),
            models.Index(fields=["company", "customer_type", "created_at"], name="ix_billdoc_ctype"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="uniq_bill_idempotency_per_company",
            ),
            models.UniqueConstraint(
                fields=["company", "branch", "doc_type", "series", "number"],
                condition=~models.Q(number=0),
                name="uniq_bill_number",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.customer_party_id and self.company_id:
            if self.customer_party.company_id != self.company_id:
                raise ValidationError({"customer_party": "customer_party debe pertenecer a la misma company."})

    @property
    def is_paid(self) -> bool:
        return self.amount_paid >= self.total

    def recalculate_payment_status(self) -> None:
        if self.amount_paid <= Decimal("0.00"):
            self.payment_status = PaymentStatus.UNPAID
        elif self.amount_paid < self.total:
            self.payment_status = PaymentStatus.PARTIAL
        elif self.amount_paid == self.total:
            self.payment_status = PaymentStatus.PAID
        else:
            self.payment_status = PaymentStatus.OVERPAID


# ---------------------------------------------------------------------------
# BillingLine
# ---------------------------------------------------------------------------

class BillingLine(models.Model):
    doc = models.ForeignKey(BillingDocument, on_delete=models.CASCADE, related_name="lines")

    description = models.CharField(max_length=200)
    quantity = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("1.0000"))
    unit_price = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal("0.000000"))
    tax_rate = models.DecimalField(max_digits=8, decimal_places=4, default=Decimal("0.0000"))

    discount_pct = models.DecimalField(
        max_digits=6, decimal_places=4, default=Decimal("0.0000"),
        help_text="Descuento en % (ej. 10.0000 = 10%)"
    )
    discount_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

    line_gross = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    line_subtotal = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    line_tax = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    line_total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

    inventory_item = models.ForeignKey(
        "inventarios.InventoryItem", null=True, blank=True,
        on_delete=models.PROTECT, related_name="billing_lines",
    )
    warehouse = models.ForeignKey(
        "inventarios.Warehouse", null=True, blank=True,
        on_delete=models.PROTECT, related_name="billing_lines",
    )
    lot = models.ForeignKey(
        "inventarios.ItemLot", null=True, blank=True,
        on_delete=models.PROTECT, related_name="billing_lines",
    )
    uom = models.CharField(max_length=16, blank=True, default="")
    uom_factor = models.DecimalField(max_digits=14, decimal_places=6, default=Decimal("1.000000"))

    class Meta:
        app_label = "facturacion"
        indexes = [
            models.Index(fields=["doc"], name="ix_billine_doc"),
        ]


# ---------------------------------------------------------------------------
# BillingPayment — múltiples pagos por documento
# ---------------------------------------------------------------------------

class BillingPayment(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pendiente"
        CONFIRMED = "CONFIRMED", "Confirmado"
        REVERSED = "REVERSED", "Revertido"

    doc = models.ForeignKey(BillingDocument, on_delete=models.PROTECT, related_name="payments")
    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="billing_payments_company")

    payment_method = models.CharField(max_length=24, choices=TENDER_PAYMENT_METHOD_CHOICES)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    currency = models.CharField(max_length=8, default="NIO")

    reference = models.CharField(max_length=96, blank=True, default="")
    notes = models.CharField(max_length=255, blank=True, default="")
    payment_date = models.DateField(default=timezone.localdate)

    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    reversal_reason = models.CharField(max_length=255, blank=True, default="")
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="billing_payments_reversed"
    )

    payroll_period_ref = models.CharField(max_length=64, blank=True, default="")
    coffee_lot_ref = models.CharField(max_length=64, blank=True, default="")

    payment_intent = models.ForeignKey(
        "payments.PaymentIntent", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="billing_payments"
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="billing_payments_created"
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        app_label = "facturacion"
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="ck_billpay_amount_positive"),
        ]
        indexes = [
            models.Index(fields=["doc", "status"], name="ix_billpay_doc_st"),
            models.Index(fields=["company", "payment_method", "payment_date"], name="ix_billpay_c_pm_pd"),
            models.Index(fields=["company", "status", "created_at"], name="ix_billpay_c_st_ca"),
        ]


# ---------------------------------------------------------------------------
# BranchFiscalConfig
# ---------------------------------------------------------------------------

class BranchFiscalConfig(models.Model):
    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="bill_fiscal_cfg_company")
    branch = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="bill_fiscal_cfg_branch")
    fiscal_mode = models.CharField(max_length=8, choices=FiscalMode.choices, default=FiscalMode.NOOP)
    adapter_code = models.CharField(max_length=32, blank=True, default="")
    print_required = models.BooleanField(default=True)
    strict_integrity = models.BooleanField(default=True)
    contingency_max_attempts = models.PositiveSmallIntegerField(default=5)
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        app_label = "facturacion"
        constraints = [
            models.UniqueConstraint(fields=["company", "branch"], name="uniq_bill_fiscal_cfg_company_branch"),
        ]
        indexes = [
            models.Index(fields=["company", "branch", "is_active"], name="ix_billfcfg_c_b_a"),
        ]


# ---------------------------------------------------------------------------
# FiscalPrintJob
# ---------------------------------------------------------------------------

class FiscalPrintJob(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pendiente"
        RETRY = "RETRY", "Reintento"
        PRINTED = "PRINTED", "Impreso"
        FAILED = "FAILED", "Fallido"

    doc = models.ForeignKey(BillingDocument, on_delete=models.CASCADE, related_name="fiscal_print_jobs")
    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="bill_print_jobs_company")
    branch = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="bill_print_jobs_branch")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    attempt_count = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=255, blank=True, default="")
    idempotency_key = models.CharField(max_length=96, blank=True, default="")
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "facturacion"
        indexes = [
            models.Index(fields=["status", "next_attempt_at", "created_at"], name="ix_billfpj_st_na_ca"),
            models.Index(fields=["company", "branch", "status", "created_at"], name="ix_billfpj_c_b_st_ca"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["doc", "idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="uniq_bill_print_job_doc_idempotency",
            ),
        ]
