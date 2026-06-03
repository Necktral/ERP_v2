"""Capa de Actividad/Tiempo (Fase 0 — fundación transversal).

Complementa la auditoría append-only de seguridad (`apps.modulos.audit`) con una
dimensión de **actividad/uso** de alto volumen y **tiempo trabajado**:

- DeviceRegistry: dispositivos conocidos por usuario (web/móvil/POS/edge).
- UserSession: sesión de uso (login -> logout) con device/ip/user-agent y duración.
- ActivityEvent: telemetría ligera por acción (ruta/método/duración). NO se
  encadena ni firma (a diferencia de AuditEvent) para no degradar rendimiento.
- WorkSession: marca de entrada/salida (clock-in/out) y horas trabajadas, para
  RRHH/operación y como insumo de nómina.
"""
from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.modulos.iam.models import OrgUnit


class DevicePlatform(models.TextChoices):
    WEB = "WEB", "Web"
    ANDROID = "ANDROID", "Android"
    IOS = "IOS", "iOS"
    POS = "POS", "Punto de venta"
    EDGE = "EDGE", "Edge/Conector"
    UNKNOWN = "UNKNOWN", "Desconocido"


class DeviceRegistry(models.Model):
    """Dispositivo conocido por usuario (identidad estable por fingerprint)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="known_devices")
    fingerprint = models.CharField(max_length=128)
    label = models.CharField(max_length=120, blank=True, default="")
    platform = models.CharField(max_length=16, choices=DevicePlatform.choices, default=DevicePlatform.UNKNOWN)
    trusted = models.BooleanField(default=False)

    first_seen_at = models.DateTimeField(default=timezone.now, editable=False)
    last_seen_at = models.DateTimeField(default=timezone.now)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = "activity"
        constraints = [
            models.UniqueConstraint(fields=["user", "fingerprint"], name="uq_device_user_fingerprint"),
        ]
        indexes = [
            models.Index(fields=["user", "revoked_at"]),
            models.Index(fields=["last_seen_at"]),
        ]

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    def __str__(self) -> str:
        return f"{self.user_id}:{self.platform}:{self.fingerprint[:12]}"


class UserSession(models.Model):
    """Sesión de uso (login -> logout) con contexto de dispositivo y duración."""

    class EndReason(models.TextChoices):
        LOGOUT = "LOGOUT", "Logout"
        EXPIRED = "EXPIRED", "Expirada"
        REVOKED = "REVOKED", "Revocada"
        REPLACED = "REPLACED", "Reemplazada"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="activity_sessions")
    device = models.ForeignKey(
        DeviceRegistry, null=True, blank=True, on_delete=models.SET_NULL, related_name="sessions"
    )
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default="")
    company_id = models.BigIntegerField(null=True, blank=True)
    branch_id = models.BigIntegerField(null=True, blank=True)
    refresh_jti = models.CharField(max_length=64, blank=True, default="")

    started_at = models.DateTimeField(default=timezone.now, editable=False)
    last_seen_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)
    end_reason = models.CharField(max_length=16, choices=EndReason.choices, blank=True, default="")

    class Meta:
        app_label = "activity"
        indexes = [
            models.Index(fields=["user", "ended_at"]),
            models.Index(fields=["started_at"]),
            models.Index(fields=["refresh_jti"]),
        ]

    @property
    def is_active(self) -> bool:
        return self.ended_at is None

    @property
    def duration_seconds(self) -> int:
        end = self.ended_at or timezone.now()
        return max(0, int((end - self.started_at).total_seconds()))

    def __str__(self) -> str:
        return f"session:{self.user_id}:{self.started_at:%Y-%m-%d %H:%M}"


class ActivityEvent(models.Model):
    """Telemetría ligera por acción (alto volumen, sin encadenamiento/firma)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="activity_events"
    )
    session = models.ForeignKey(
        UserSession, null=True, blank=True, on_delete=models.SET_NULL, related_name="events"
    )
    device = models.ForeignKey(
        DeviceRegistry, null=True, blank=True, on_delete=models.SET_NULL, related_name="events"
    )
    company_id = models.BigIntegerField(null=True, blank=True)
    branch_id = models.BigIntegerField(null=True, blank=True)

    route = models.CharField(max_length=255, blank=True, default="")
    method = models.CharField(max_length=16, blank=True, default="")
    status_code = models.PositiveSmallIntegerField(default=0)
    duration_ms = models.PositiveIntegerField(default=0)
    request_id = models.CharField(max_length=64, blank=True, default="")

    occurred_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        app_label = "activity"
        indexes = [
            models.Index(fields=["user", "occurred_at"]),
            models.Index(fields=["company_id", "occurred_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.method} {self.route} ({self.status_code})"


class WorkSession(models.Model):
    """Marca de entrada/salida (clock-in/out) y horas trabajadas."""

    class Source(models.TextChoices):
        WEB = "WEB", "Web"
        POS = "POS", "Punto de venta"
        KIOSK = "KIOSK", "Kiosco"
        MANUAL = "MANUAL", "Manual"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="work_sessions")
    company = models.ForeignKey(OrgUnit, on_delete=models.PROTECT, related_name="work_sessions_company")
    branch = models.ForeignKey(
        OrgUnit, null=True, blank=True, on_delete=models.PROTECT, related_name="work_sessions_branch"
    )

    source = models.CharField(max_length=16, choices=Source.choices, default=Source.WEB)
    note = models.CharField(max_length=255, blank=True, default="")

    clock_in = models.DateTimeField(default=timezone.now)
    clock_out = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = "activity"
        constraints = [
            # Una sola sesión de trabajo abierta por usuario+empresa.
            models.UniqueConstraint(
                fields=["user", "company"],
                condition=models.Q(clock_out__isnull=True),
                name="uq_open_work_session_user_company",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "clock_out"]),
            models.Index(fields=["company", "branch", "clock_in"]),
        ]

    @property
    def is_open(self) -> bool:
        return self.clock_out is None

    @property
    def hours_worked(self) -> Decimal:
        if self.clock_out is None:
            return Decimal("0.00")
        seconds = (self.clock_out - self.clock_in).total_seconds()
        return (Decimal(str(seconds)) / Decimal("3600")).quantize(Decimal("0.01"))

    def __str__(self) -> str:
        return f"work:{self.user_id}@{self.company_id}:{self.clock_in:%Y-%m-%d %H:%M}"
