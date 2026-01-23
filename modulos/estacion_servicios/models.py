from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class FuelProduct(models.TextChoices):
    DIESEL = "DIESEL", "Diesel"
    GASOLINE = "GASOLINE", "Gasolina"


class FuelShiftStatus(models.TextChoices):
    OPEN = "OPEN", "Abierto"
    CLOSED = "CLOSED", "Cerrado"


class FuelSaleStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Activa"
    CANCELLED = "CANCELLED", "Anulada"


class FuelSaleType(models.TextChoices):
    INTERNAL = "INTERNAL", "Consumo interno"
    PUBLIC = "PUBLIC", "Venta al público"
    EMPLOYEE = "EMPLOYEE", "Empleado (crédito/abonos)"


class FuelPaymentMethod(models.TextChoices):
    CASH = "CASH", "Efectivo"
    TRANSFER = "TRANSFER", "Transferencia"
    CREDIT = "CREDIT", "Crédito"


class FuelShift(models.Model):
    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="fuel_shifts_company")
    branch = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="fuel_shifts_branch")

    status = models.CharField(max_length=16, choices=FuelShiftStatus.choices, default=FuelShiftStatus.OPEN)

    opened_at = models.DateTimeField(default=timezone.now)
    opened_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="fuel_shifts_opened")

    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="fuel_shifts_closed"
    )

    note = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        indexes = [
            models.Index(fields=["company", "branch", "status", "opened_at"]),
        ]
        constraints = [
            # Un solo turno abierto por sucursal
            models.UniqueConstraint(
                fields=["branch"],
                condition=models.Q(status=FuelShiftStatus.OPEN),
                name="uniq_open_shift_per_branch",
            )
        ]


class FuelDispense(models.Model):
    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="fuel_dispenses_company")
    branch = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="fuel_dispenses_branch")
    shift = models.ForeignKey(FuelShift, on_delete=models.PROTECT, related_name="dispenses")

    occurred_at = models.DateTimeField(default=timezone.now)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="fuel_dispenses")

    product = models.CharField(max_length=16, choices=FuelProduct.choices)

    liters = models.DecimalField(max_digits=12, decimal_places=3)
    unit_price = models.DecimalField(max_digits=12, decimal_places=4)
    amount = models.DecimalField(max_digits=14, decimal_places=2)

    vehicle_plate = models.CharField(max_length=32, blank=True, default="")
    vehicle_ref = models.CharField(max_length=64, blank=True, default="")  # número interno, flota, lo que uses
    driver_name = models.CharField(max_length=120, blank=True, default="")

    pump_code = models.CharField(max_length=32, blank=True, default="")
    nozzle_code = models.CharField(max_length=32, blank=True, default="")
    meter_reading = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)

    external_ref = models.CharField(max_length=64, blank=True, default="")  # "pedido", "orden", "vale", tu correlativo
    note = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        indexes = [
            models.Index(fields=["company", "branch", "occurred_at"]),
            models.Index(fields=["shift", "occurred_at"]),
            models.Index(fields=["product", "occurred_at"]),
        ]


class FuelSale(models.Model):
    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="fuel_sales_company")
    branch = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="fuel_sales_branch")
    shift = models.ForeignKey(FuelShift, on_delete=models.PROTECT, related_name="sales")

    dispense = models.OneToOneField(FuelDispense, on_delete=models.PROTECT, related_name="sale")

    sale_type = models.CharField(max_length=16, choices=FuelSaleType.choices)
    payment_method = models.CharField(max_length=16, choices=FuelPaymentMethod.choices)

    # “party snapshot” mínimo (sin depender aún del módulo de clientes)
    customer_name = models.CharField(max_length=200, blank=True, default="")
    customer_ref = models.CharField(max_length=64, blank=True, default="")  # cédula, código cliente, interno, lo que uses

    total_amount = models.DecimalField(max_digits=14, decimal_places=2)

    status = models.CharField(max_length=16, choices=FuelSaleStatus.choices, default=FuelSaleStatus.ACTIVE)

    created_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="fuel_sales_created")

    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="fuel_sales_cancelled"
    )
    cancel_reason = models.CharField(max_length=255, blank=True, default="")

    is_fiscal = models.BooleanField(default=False)  # preparado para el futuro

    class Meta:
        indexes = [
            models.Index(fields=["company", "branch", "created_at"]),
            models.Index(fields=["status", "created_at"]),
        ]
