"""Flota/Mantenimiento — Fase A: datos maestros + cumplimiento.

Activos (vehículo/maquinaria/estacionario), conductores, taxonomía de mantenimiento
(tipo→plan→regla) con estado por activo, y documentos con vencimiento. Sin dinero,
sin telemetría, sin órdenes de trabajo (esos son fases siguientes). Cada empresa
(RUC propio) es dueña de sus activos.
"""
from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.modulos.iam.models import OrgUnit


# ---------------------------------------------------------------------------
# Perfil del vehículo / activo
# ---------------------------------------------------------------------------

class AssetType(models.TextChoices):
    VEHICLE = "VEHICLE", "Vehículo"
    MACHINERY = "MACHINERY", "Maquinaria"
    STATIONARY = "STATIONARY", "Estacionario"


class FuelType(models.TextChoices):
    DIESEL = "DIESEL", "Diésel"
    GASOLINE = "GASOLINE", "Gasolina"
    NONE = "NONE", "N/A"


class MeterBasis(models.TextChoices):
    ODOMETER_KM = "ODOMETER_KM", "Odómetro (km)"
    HOURMETER = "HOURMETER", "Horómetro (h)"


class ObdProtocol(models.TextChoices):
    NONE = "NONE", "Sin OBD"
    OBD2_12V = "OBD2_12V", "OBD-II 12V"
    J1939_24V = "J1939_24V", "J1939 24V"


class AssetStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Activo"
    IN_SERVICE = "IN_SERVICE", "En servicio"
    MAINTENANCE_DUE = "MAINTENANCE_DUE", "Mantenimiento vencido"
    IN_MAINTENANCE = "IN_MAINTENANCE", "En mantenimiento"
    OUT_OF_SERVICE = "OUT_OF_SERVICE", "Fuera de servicio"
    RETIRED = "RETIRED", "De baja"


class FleetAsset(models.Model):
    company = models.ForeignKey(OrgUnit, on_delete=models.PROTECT, related_name="fleet_assets")
    branch = models.ForeignKey(
        OrgUnit, null=True, blank=True, on_delete=models.PROTECT, related_name="fleet_assets_branch"
    )
    asset_type = models.CharField(max_length=12, choices=AssetType.choices)
    code = models.CharField(max_length=64, help_text="Número/código interno del activo.")
    name = models.CharField(max_length=160)
    plate = models.CharField(max_length=32, blank=True, default="")
    vin = models.CharField(max_length=64, blank=True, default="")
    make = models.CharField(max_length=80, blank=True, default="")
    model = models.CharField(max_length=80, blank=True, default="")
    year = models.PositiveSmallIntegerField(null=True, blank=True)
    engine_desc = models.CharField(max_length=160, blank=True, default="")
    fuel_type = models.CharField(max_length=10, choices=FuelType.choices, default=FuelType.DIESEL)
    tank_capacity_l = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))

    meter_basis = models.CharField(max_length=12, choices=MeterBasis.choices, default=MeterBasis.ODOMETER_KM)
    current_odometer_km = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    current_hourmeter = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    # Telemetría (Fase C): se captura ya para no migrar después.
    has_obd = models.BooleanField(default=False)
    obd_protocol = models.CharField(max_length=12, choices=ObdProtocol.choices, default=ObdProtocol.NONE)

    status = models.CharField(max_length=16, choices=AssetStatus.choices, default=AssetStatus.ACTIVE, db_index=True)
    notes = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "fleet"
        constraints = [
            models.UniqueConstraint(fields=["company", "code"], name="uq_fleet_asset_company_code"),
        ]
        indexes = [
            models.Index(fields=["company", "asset_type", "status"], name="ix_asset_co_type_status"),
        ]

    def clean(self):
        super().clean()
        if self.company_id and self.company.unit_type != OrgUnit.UnitType.COMPANY:
            raise ValidationError({"company": "company debe ser OrgUnit de tipo COMPANY."})

    def __str__(self) -> str:
        return f"FleetAsset<{self.code}:{self.asset_type}>"


# ---------------------------------------------------------------------------
# Perfil del conductor
# ---------------------------------------------------------------------------

class DriverStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Activo"
    SUSPENDED = "SUSPENDED", "Suspendido"
    INACTIVE = "INACTIVE", "Inactivo"


class Driver(models.Model):
    company = models.ForeignKey(OrgUnit, on_delete=models.PROTECT, related_name="fleet_drivers")
    employee = models.ForeignKey(
        "hr.Employee", null=True, blank=True, on_delete=models.SET_NULL, related_name="fleet_driver_profiles",
        help_text="Opcional: enlaza al empleado; null = conductor externo/contratista.",
    )
    full_name = models.CharField(max_length=160)
    national_id = models.CharField(max_length=32, blank=True, default="")
    license_number = models.CharField(max_length=64, blank=True, default="")
    license_category = models.CharField(max_length=16, blank=True, default="")
    license_expiry = models.DateField(null=True, blank=True)
    phone = models.CharField(max_length=64, blank=True, default="")
    status = models.CharField(max_length=12, choices=DriverStatus.choices, default=DriverStatus.ACTIVE)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "fleet"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "license_number"],
                condition=~models.Q(license_number=""),
                name="uq_fleet_driver_company_license",
            ),
        ]
        indexes = [
            models.Index(fields=["company", "is_active"], name="ix_driver_co_active"),
        ]

    def __str__(self) -> str:
        return f"Driver<{self.full_name}>"


class DriverAssignment(models.Model):
    asset = models.ForeignKey(FleetAsset, on_delete=models.CASCADE, related_name="driver_assignments")
    driver = models.ForeignKey(Driver, on_delete=models.PROTECT, related_name="assignments")
    assigned_at = models.DateTimeField(default=timezone.now)
    released_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        app_label = "fleet"
        indexes = [
            models.Index(fields=["asset", "is_active"], name="ix_driverasg_asset_active"),
            models.Index(fields=["driver", "is_active"], name="ix_driverasg_driver_active"),
        ]

    def __str__(self) -> str:
        return f"DriverAssignment<{self.asset_id}:{self.driver_id}>"


# ---------------------------------------------------------------------------
# Taxonomía de mantenimiento: tipo → plan → regla → estado por activo
# ---------------------------------------------------------------------------

class MaintenanceKind(models.TextChoices):
    PREVENTIVE = "PREVENTIVE", "Preventivo"
    CORRECTIVE = "CORRECTIVE", "Correctivo"
    PREDICTIVE = "PREDICTIVE", "Predictivo"


class TriggerBasis(models.TextChoices):
    KM = "KM", "Por kilómetros"
    HOURS = "HOURS", "Por horas"
    TIME = "TIME", "Por tiempo"
    CONDITION = "CONDITION", "Por condición"


class MaintenanceType(models.Model):
    company = models.ForeignKey(OrgUnit, on_delete=models.PROTECT, related_name="maintenance_types")
    code = models.CharField(max_length=48)
    name = models.CharField(max_length=160)
    kind = models.CharField(max_length=12, choices=MaintenanceKind.choices, default=MaintenanceKind.PREVENTIVE)
    trigger_basis = models.CharField(max_length=12, choices=TriggerBasis.choices, default=TriggerBasis.KM)
    default_action = models.CharField(max_length=255, blank=True, default="")
    is_active = models.BooleanField(default=True)

    class Meta:
        app_label = "fleet"
        constraints = [
            models.UniqueConstraint(fields=["company", "code"], name="uq_maint_type_company_code"),
        ]

    def __str__(self) -> str:
        return f"MaintenanceType<{self.code}>"


class MaintenancePlan(models.Model):
    company = models.ForeignKey(OrgUnit, on_delete=models.PROTECT, related_name="maintenance_plans")
    name = models.CharField(max_length=160)
    asset_class = models.CharField(
        max_length=32, blank=True, default="",
        help_text="Clase a la que aplica (moto/liviano/camión/maquinaria/estacionario); vacío = libre.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        app_label = "fleet"
        indexes = [models.Index(fields=["company", "is_active"], name="ix_maintplan_co_active")]

    def __str__(self) -> str:
        return f"MaintenancePlan<{self.name}>"


class MaintenanceRule(models.Model):
    plan = models.ForeignKey(MaintenancePlan, on_delete=models.CASCADE, related_name="rules")
    maintenance_type = models.ForeignKey(MaintenanceType, on_delete=models.PROTECT, related_name="rules")
    trigger_basis = models.CharField(max_length=12, choices=TriggerBasis.choices, default=TriggerBasis.KM)
    interval_km = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    interval_hours = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    interval_days = models.PositiveIntegerField(null=True, blank=True)
    severity_factor = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal("1.00"))
    recommended_action = models.CharField(max_length=255, blank=True, default="")
    is_active = models.BooleanField(default=True)

    class Meta:
        app_label = "fleet"
        indexes = [models.Index(fields=["plan", "is_active"], name="ix_maintrule_plan_active")]

    def __str__(self) -> str:
        return f"MaintenanceRule<{self.plan_id}:{self.maintenance_type_id}>"


class AssetMaintenanceState(models.Model):
    """Materialización por activo de una regla de plan: próximo vencimiento + flag de vencido."""

    asset = models.ForeignKey(FleetAsset, on_delete=models.CASCADE, related_name="maintenance_states")
    rule = models.ForeignKey(MaintenanceRule, on_delete=models.CASCADE, related_name="asset_states")
    next_due_km = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    next_due_hours = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    next_due_date = models.DateField(null=True, blank=True)
    is_due = models.BooleanField(default=False)
    last_done_at = models.DateTimeField(null=True, blank=True)
    last_flagged_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = "fleet"
        constraints = [
            models.UniqueConstraint(fields=["asset", "rule"], name="uq_asset_maint_state"),
        ]
        indexes = [models.Index(fields=["asset", "is_due"], name="ix_maintstate_asset_due")]

    def __str__(self) -> str:
        return f"AssetMaintenanceState<{self.asset_id}:{self.rule_id}>"


# ---------------------------------------------------------------------------
# Documentación (con vencimiento → alerta)
# ---------------------------------------------------------------------------

class DocumentType(models.TextChoices):
    INSURANCE = "INSURANCE", "Seguro"
    CIRCULATION = "CIRCULATION", "Circulación"
    LICENSE = "LICENSE", "Licencia"
    TECH_REVIEW = "TECH_REVIEW", "Revisión técnica"
    OTHER = "OTHER", "Otro"


class DocumentStatus(models.TextChoices):
    VALID = "VALID", "Vigente"
    EXPIRING = "EXPIRING", "Por vencer"
    EXPIRED = "EXPIRED", "Vencido"


class FleetDocument(models.Model):
    company = models.ForeignKey(OrgUnit, on_delete=models.PROTECT, related_name="fleet_documents")
    asset = models.ForeignKey(
        FleetAsset, null=True, blank=True, on_delete=models.CASCADE, related_name="documents"
    )
    driver = models.ForeignKey(
        Driver, null=True, blank=True, on_delete=models.CASCADE, related_name="documents"
    )
    doc_type = models.CharField(max_length=16, choices=DocumentType.choices)
    number = models.CharField(max_length=96, blank=True, default="")
    issuer = models.CharField(max_length=160, blank=True, default="")
    issue_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True, db_index=True)
    file_ref = models.CharField(max_length=512, blank=True, default="", help_text="URL/Drive/evidence (no blob).")
    status = models.CharField(max_length=10, choices=DocumentStatus.choices, default=DocumentStatus.VALID)
    notes = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "fleet"
        constraints = [
            models.CheckConstraint(
                condition=(
                    (models.Q(asset__isnull=False) & models.Q(driver__isnull=True))
                    | (models.Q(asset__isnull=True) & models.Q(driver__isnull=False))
                ),
                name="ck_fleetdoc_exactly_one_owner",
            ),
        ]
        indexes = [
            models.Index(fields=["company", "expiry_date"], name="ix_fleetdoc_co_expiry"),
            models.Index(fields=["company", "doc_type", "status"], name="ix_fleetdoc_co_type_status"),
        ]

    def clean(self):
        super().clean()
        if bool(self.asset_id) == bool(self.driver_id):
            raise ValidationError("El documento debe pertenecer a exactamente uno: activo o conductor.")

    def __str__(self) -> str:
        return f"FleetDocument<{self.doc_type}:{self.asset_id or self.driver_id}>"
