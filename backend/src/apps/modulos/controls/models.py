"""Modelos del control plane anti-fraude (Capa 3).

`SegregationRule` declara combinaciones tóxicas de permisos (matriz SoD).
`ControlFinding` materializa violaciones detectadas (por concesión o por
ejercicio) como hallazgos revisables. La detección y la auditoría viven en
`services.py`; aquí solo el dato y sus invariantes.
"""
from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.modulos.iam.models import OrgUnit


class Severity(models.TextChoices):
    LOW = "LOW", "Baja"
    MEDIUM = "MEDIUM", "Media"
    HIGH = "HIGH", "Alta"
    CRITICAL = "CRITICAL", "Crítica"


class SegregationRule(models.Model):
    """Par de permisos incompatibles (segregación de funciones).

    `company` nulo = regla global (catálogo estándar). `permission_a/b` se usan
    para la detección por concesión (el usuario posee ambos); `event_a/b`
    (opcionales) para la detección por ejercicio (el usuario realizó ambas
    acciones en el audit log).
    """

    class Meta:
        app_label = "controls"
        constraints = [
            models.UniqueConstraint(fields=["company", "code"], name="uq_segrule_company_code"),
            models.UniqueConstraint(
                fields=["code"], condition=models.Q(company__isnull=True), name="uq_segrule_global_code"
            ),
        ]
        indexes = [
            models.Index(fields=["company", "is_active"]),
        ]

    company = models.ForeignKey(
        OrgUnit, null=True, blank=True, on_delete=models.PROTECT, related_name="segregation_rules"
    )
    code = models.CharField(max_length=64)
    name = models.CharField(max_length=200)
    permission_a = models.CharField(max_length=128)
    permission_b = models.CharField(max_length=128)
    event_a = models.CharField(max_length=64, blank=True, default="")
    event_b = models.CharField(max_length=64, blank=True, default="")
    severity = models.CharField(max_length=16, choices=Severity.choices, default=Severity.HIGH)
    rationale = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        if self.company_id and self.company.unit_type != OrgUnit.UnitType.COMPANY:
            raise ValidationError("SegregationRule.company debe ser OrgUnit de tipo COMPANY (o nulo = global).")
        if self.permission_a == self.permission_b:
            raise ValidationError("Una regla SoD requiere dos permisos distintos.")

    def __str__(self) -> str:
        return f"{self.code} ({self.permission_a} × {self.permission_b})"


class ControlFinding(models.Model):
    """Hallazgo de control detectado, con workflow de revisión."""

    class ControlCode(models.TextChoices):
        SOD_GRANT = "SOD_GRANT", "SoD por concesión"
        SOD_EXERCISED = "SOD_EXERCISED", "SoD por ejercicio"

    class Status(models.TextChoices):
        OPEN = "OPEN", "Abierto"
        ACKNOWLEDGED = "ACKNOWLEDGED", "Reconocido"
        RESOLVED = "RESOLVED", "Resuelto"
        DISMISSED = "DISMISSED", "Descartado"

    class Meta:
        app_label = "controls"
        constraints = [
            models.UniqueConstraint(fields=["company", "dedup_key"], name="uq_finding_company_dedup"),
        ]
        indexes = [
            models.Index(fields=["company", "status", "-detected_at"]),
            models.Index(fields=["company", "control_code", "status"]),
            models.Index(fields=["actor_user", "-detected_at"]),
        ]

    company = models.ForeignKey(OrgUnit, on_delete=models.PROTECT, related_name="control_findings")
    control_code = models.CharField(max_length=32, choices=ControlCode.choices)
    rule = models.ForeignKey(
        SegregationRule, null=True, blank=True, on_delete=models.SET_NULL, related_name="findings"
    )
    severity = models.CharField(max_length=16, choices=Severity.choices, default=Severity.HIGH)
    actor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="control_findings"
    )
    subject_type = models.CharField(max_length=32, blank=True, default="")
    subject_id = models.CharField(max_length=128, blank=True, default="")
    detail = models.JSONField(default=dict, blank=True)

    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    dedup_key = models.CharField(max_length=200)
    detected_at = models.DateTimeField(default=timezone.now, editable=False)

    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="control_findings_resolved",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_note = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    _TERMINAL = frozenset({Status.RESOLVED, Status.DISMISSED})

    def clean(self):
        if self.company_id and self.company.unit_type != OrgUnit.UnitType.COMPANY:
            raise ValidationError("ControlFinding.company debe ser OrgUnit de tipo COMPANY.")

    def __str__(self) -> str:
        return f"{self.control_code} [{self.status}] {self.dedup_key}"
