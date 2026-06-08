"""Modelos de Manejo de Fincas (Capa 6, básico).

Master-data (FincaProfile, Plot, Labor) + planificación/bitácora (WorkOrder) +
insumos (InsumoApplication). No recaptura asistencia: la captura de campo vive
en `kernels.nomina`. La detección/costeo y la auditoría viven en `services.py`.
"""
from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.modulos.iam.models import OrgUnit


class LaborCategory(models.TextChoices):
    ESTABLECIMIENTO = "ESTABLECIMIENTO", "Establecimiento"
    MANTENIMIENTO = "MANTENIMIENTO", "Mantenimiento"
    SANIDAD = "SANIDAD", "Sanidad"
    COSECHA = "COSECHA", "Cosecha"
    BENEFICIADO = "BENEFICIADO", "Beneficiado"
    INFRAESTRUCTURA = "INFRAESTRUCTURA", "Infraestructura"


class LaborUnit(models.TextChoices):
    JORNAL = "JORNAL", "Jornal"
    MANZANA = "MANZANA", "Manzana"
    LATA = "LATA", "Lata"
    QUINTAL = "QUINTAL", "Quintal"
    HORA = "HORA", "Hora"


class FincaProfile(models.Model):
    """Geografía y metadatos de una finca (OrgUnit BRANCH)."""

    class Meta:
        app_label = "finca"
        indexes = [models.Index(fields=["zona"])]

    finca = models.OneToOneField(OrgUnit, on_delete=models.CASCADE, related_name="finca_profile")
    department = models.CharField(max_length=120, blank=True, default="")
    municipio = models.CharField(max_length=120, blank=True, default="")
    zona = models.CharField(max_length=160, blank=True, default="")
    area_manzanas = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    is_headquarters = models.BooleanField(default=False)
    gps_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    gps_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        if self.finca_id and self.finca.unit_type != OrgUnit.UnitType.BRANCH:
            raise ValidationError("FincaProfile.finca debe ser OrgUnit de tipo BRANCH.")

    def __str__(self) -> str:
        return f"Finca {self.finca_id} ({self.zona})"


class Plot(models.Model):
    """Lote de una finca."""

    class Meta:
        app_label = "finca"
        constraints = [models.UniqueConstraint(fields=["finca", "code"], name="uq_plot_finca_code")]
        indexes = [models.Index(fields=["finca", "is_active"])]

    finca = models.ForeignKey(OrgUnit, on_delete=models.PROTECT, related_name="plots")
    code = models.CharField(max_length=64)
    name = models.CharField(max_length=160, blank=True, default="")
    area_manzanas = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    crop = models.CharField(max_length=40, default="CAFE")
    variety = models.CharField(max_length=120, blank=True, default="")
    planting_year = models.PositiveIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        if self.finca_id and self.finca.unit_type != OrgUnit.UnitType.BRANCH:
            raise ValidationError("Plot.finca debe ser OrgUnit de tipo BRANCH.")

    def __str__(self) -> str:
        return f"{self.code} ({self.name})"


class Labor(models.Model):
    """Catálogo de labores. `company` nulo = global (catálogo estándar editable)."""

    class Meta:
        app_label = "finca"
        constraints = [
            models.UniqueConstraint(fields=["company", "code"], name="uq_labor_company_code"),
            models.UniqueConstraint(
                fields=["code"], condition=models.Q(company__isnull=True), name="uq_labor_global_code"
            ),
        ]
        indexes = [models.Index(fields=["company", "category", "is_active"])]

    company = models.ForeignKey(
        OrgUnit, null=True, blank=True, on_delete=models.PROTECT, related_name="finca_labors"
    )
    code = models.CharField(max_length=64)
    name = models.CharField(max_length=160)
    category = models.CharField(max_length=24, choices=LaborCategory.choices, default=LaborCategory.MANTENIMIENTO)
    unit = models.CharField(max_length=16, choices=LaborUnit.choices, default=LaborUnit.JORNAL)
    is_piecework = models.BooleanField(default=False)
    expected_yield = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    default_rate = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        if self.company_id and self.company.unit_type != OrgUnit.UnitType.COMPANY:
            raise ValidationError("Labor.company debe ser OrgUnit de tipo COMPANY (o nulo = global).")

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"


class WorkOrder(models.Model):
    """Orden de trabajo / bitácora: una labor en un lote (plan + cierre)."""

    class Status(models.TextChoices):
        PLANNED = "PLANNED", "Planificada"
        IN_PROGRESS = "IN_PROGRESS", "En proceso"
        DONE = "DONE", "Hecha"
        CANCELLED = "CANCELLED", "Cancelada"

    class Meta:
        app_label = "finca"
        constraints = [
            models.UniqueConstraint(
                fields=["finca", "external_ref"],
                condition=~models.Q(external_ref=""),
                name="uq_workorder_finca_extref",
            ),
        ]
        indexes = [
            models.Index(fields=["finca", "status"]),
            models.Index(fields=["plot", "labor"]),
            models.Index(fields=["season_label"]),
        ]

    finca = models.ForeignKey(OrgUnit, on_delete=models.PROTECT, related_name="work_orders")
    plot = models.ForeignKey(Plot, on_delete=models.PROTECT, related_name="work_orders")
    labor = models.ForeignKey(Labor, on_delete=models.PROTECT, related_name="work_orders")
    season_label = models.CharField(max_length=80, blank=True, default="")
    planned_date = models.DateField(null=True, blank=True)
    done_date = models.DateField(null=True, blank=True)
    supervisor = models.ForeignKey(
        "hr.Employee", null=True, blank=True, on_delete=models.SET_NULL, related_name="finca_work_orders"
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PLANNED, db_index=True)
    target_quantity = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    actual_quantity = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    jornales = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    notes = models.TextField(blank=True, default="")
    external_ref = models.CharField(max_length=128, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="finca_work_orders"
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        if self.finca_id and self.finca.unit_type != OrgUnit.UnitType.BRANCH:
            raise ValidationError("WorkOrder.finca debe ser OrgUnit de tipo BRANCH.")
        if self.plot_id and self.finca_id and self.plot.finca_id != self.finca_id:
            raise ValidationError("WorkOrder.plot debe pertenecer a la misma finca.")

    def __str__(self) -> str:
        return f"WO {self.labor_id}@{self.plot_id} [{self.status}]"


class InsumoApplication(models.Model):
    """Consumo de insumo en una orden de trabajo.

    `source=MANUAL`: registro suelto (costo digitado). `source=INVENTORY`: descontado
    de stock real vía `kernels.inventarios` (costo = promedio del movimiento), con
    referencia al `StockMovement` — sin duplicar el movimiento de inventario.
    """

    class Source(models.TextChoices):
        MANUAL = "MANUAL", "Manual"
        INVENTORY = "INVENTORY", "Inventario"

    class Meta:
        app_label = "finca"
        indexes = [models.Index(fields=["work_order"])]

    work_order = models.ForeignKey(WorkOrder, on_delete=models.CASCADE, related_name="insumos")
    source = models.CharField(max_length=16, choices=Source.choices, default=Source.MANUAL)
    item_code = models.CharField(max_length=64, blank=True, default="")
    item_name = models.CharField(max_length=160, blank=True, default="")
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    unit = models.CharField(max_length=24, blank=True, default="")
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    inventory_item_id = models.PositiveIntegerField(null=True, blank=True)
    warehouse_id = models.PositiveIntegerField(null=True, blank=True)
    stock_movement_ref = models.CharField(max_length=64, blank=True, default="")
    applied_at = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    def __str__(self) -> str:
        return f"{self.item_name} x{self.quantity}"
