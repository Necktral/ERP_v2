"""Control biométrico (fuente ① de asistencia) — ingesta, no captura.

Precedente del negocio: el aparato biométrico es un equipo especializado (un
"pequeño servidor") que recoge entrada/salida por rostro. El ERP NO hace
reconocimiento: SOLO toma la información, por dos vías:
  - Import de archivo (.xlsx/.csv) que exporta el aparato — vía principal hoy.
  - Push HTTP con token por dispositivo — para cuando el aparato/puente esté en
    la WiFi de la hacienda.

Regla de pago: la ENTRADA valida el día; la salida difiere por las distancias
del campo pero cuenta como chequeo/evidencia. El rollup alimenta
AttendanceReport(source=BIOMETRIC) por período para el cruce de 3 controles.
"""

from __future__ import annotations

import secrets
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


def new_device_token() -> str:
    return secrets.token_hex(24)


class BiometricDevice(models.Model):
    """Aparato biométrico registrado (por empresa, opcionalmente por sucursal)."""

    device_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    company = models.ForeignKey(
        "iam.OrgUnit", on_delete=models.PROTECT, related_name="nomina_biometric_devices_company"
    )
    branch = models.ForeignKey(
        "iam.OrgUnit",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="nomina_biometric_devices_branch",
    )
    name = models.CharField(max_length=160)
    vendor = models.CharField(max_length=120, blank=True, default="")  # marca/modelo
    serial = models.CharField(max_length=120, blank=True, default="")
    api_token = models.CharField(max_length=64, unique=True, default=new_device_token, editable=False)
    is_active = models.BooleanField(default=True, db_index=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="nomina_biometric_devices_created",
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "nomina"
        indexes = [models.Index(fields=["company", "is_active"])]

    def __str__(self) -> str:
        return f"{self.name} ({self.company_id})"


class BiometricPersonMap(models.Model):
    """Mapeo código-del-aparato → trabajador (cuando no coincide con employee_code)."""

    company = models.ForeignKey(
        "iam.OrgUnit", on_delete=models.PROTECT, related_name="nomina_biometric_maps_company"
    )
    external_code = models.CharField(max_length=64)
    employee = models.ForeignKey("hr.Employee", on_delete=models.CASCADE, related_name="biometric_maps")
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="nomina_biometric_maps_created",
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        app_label = "nomina"
        constraints = [
            models.UniqueConstraint(fields=["company", "external_code"], name="uq_biometric_map_company_code"),
        ]
        indexes = [models.Index(fields=["company", "is_active"])]


class BiometricImportBatch(models.Model):
    """Una importación de archivo del aparato (trazabilidad + conteos)."""

    company = models.ForeignKey(
        "iam.OrgUnit", on_delete=models.PROTECT, related_name="nomina_biometric_batches_company"
    )
    device = models.ForeignKey(BiometricDevice, on_delete=models.PROTECT, related_name="import_batches")
    file_name = models.CharField(max_length=255, blank=True, default="")
    rows_total = models.PositiveIntegerField(default=0)
    created_count = models.PositiveIntegerField(default=0)
    duplicate_count = models.PositiveIntegerField(default=0)
    unmatched_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    errors = models.JSONField(default=list, blank=True)  # primeras N filas con problema
    imported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="nomina_biometric_batches_imported",
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        app_label = "nomina"
        indexes = [models.Index(fields=["company", "created_at"])]
        ordering = ["-created_at", "-id"]


class BiometricCheckDirection(models.TextChoices):
    IN = "IN", "Entrada"
    OUT = "OUT", "Salida"
    UNKNOWN = "UNKNOWN", "Sin dirección"


class BiometricCheck(models.Model):
    """Un chequeo crudo del aparato (idempotente vía dedupe_key)."""

    device = models.ForeignKey(BiometricDevice, on_delete=models.PROTECT, related_name="checks")
    company = models.ForeignKey(
        "iam.OrgUnit", on_delete=models.PROTECT, related_name="nomina_biometric_checks_company"
    )
    employee = models.ForeignKey(
        "hr.Employee",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="biometric_checks",
    )
    external_code = models.CharField(max_length=64, db_index=True)
    external_name = models.CharField(max_length=160, blank=True, default="")
    direction = models.CharField(
        max_length=8, choices=BiometricCheckDirection.choices, default=BiometricCheckDirection.UNKNOWN
    )
    checked_at = models.DateTimeField(db_index=True)
    work_date = models.DateField(db_index=True)  # fecha local del chequeo (deriva el día trabajado)
    import_batch = models.ForeignKey(
        BiometricImportBatch, null=True, blank=True, on_delete=models.SET_NULL, related_name="checks"
    )
    raw = models.JSONField(default=dict, blank=True)
    # sha256(device|external_code|checked_at|direction): reimportar o reenviar NO duplica
    dedupe_key = models.CharField(max_length=64, unique=True, editable=False)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        app_label = "nomina"
        indexes = [
            models.Index(fields=["company", "work_date"]),
            models.Index(fields=["employee", "work_date"]),
            models.Index(fields=["company", "external_code"]),
        ]
        ordering = ["-checked_at", "-id"]
