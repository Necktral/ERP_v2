"""Ledger de evidencia de errores de runtime (Mundo B — plataforma de diagnóstico).

`ErrorEvent` es la unidad de "Error Intelligence": cada error no manejado del ciclo
request/response queda como evidencia **deduplicada por `stack_hash`** (mismo stack =
misma fila, `occurrence_count++`), con su dominio y clase de riesgo Necktral (C1/C2/C3)
ya resueltos. La captura es best-effort (nunca altera la respuesta) y redacta antes de
persistir. Rebanada B-1: solo el modelo runtime; `SecurityFinding`/`CodeUnitEvidence`
y los gates llegan en rebanadas siguientes.
"""
from __future__ import annotations

import uuid

from django.db import models
from django.utils import timezone


class RiskClass(models.TextChoices):
    C1 = "C1", "C1 — dinero/stock/fiscal/permisos/CEC/auditoría"
    C2 = "C2", "C2 — confiabilidad/trazabilidad/API/reporting"
    C3 = "C3", "C3 — deuda/estilo/baja exposición"


class ErrorStatus(models.TextChoices):
    OPEN = "open", "Abierto"
    TRIAGED = "triaged", "Triado"
    CONFIRMED = "confirmed", "Confirmado"
    FIXED = "fixed", "Corregido"
    REGRESSED = "regressed", "Regresado"
    ACCEPTED_RISK = "accepted_risk", "Riesgo aceptado"
    FALSE_POSITIVE = "false_positive", "Falso positivo"


class ErrorEvent(models.Model):
    class Meta:
        app_label = "diagnostics"
        ordering = ["-last_seen_at"]
        indexes = [
            models.Index(fields=["stack_hash"]),
            models.Index(fields=["domain", "risk_class"]),
            models.Index(fields=["status", "-last_seen_at"]),
        ]

    error_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    # Identidad/dedupe.
    exception_type = models.CharField(max_length=255)
    message_hash = models.CharField(max_length=64, blank=True, default="")
    stack_hash = models.CharField(max_length=64, unique=True)
    stack_trace_redacted = models.TextField(blank=True, default="")

    # Ubicación (frame más profundo del repo).
    file_path = models.CharField(max_length=512, blank=True, default="")
    line_number = models.PositiveIntegerField(default=0)
    function_name = models.CharField(max_length=255, blank=True, default="")

    # Contexto del request.
    endpoint = models.CharField(max_length=512, blank=True, default="")
    method = models.CharField(max_length=16, blank=True, default="")
    http_status = models.PositiveSmallIntegerField(default=500)

    # Clasificación Necktral.
    domain = models.CharField(max_length=64, blank=True, default="")
    risk_class = models.CharField(
        max_length=2, choices=RiskClass.choices, default=RiskClass.C3
    )

    # Trazabilidad / tenant (desacoplado: ids como texto, no FK).
    correlation_id = models.CharField(max_length=64, blank=True, default="")
    company_id = models.CharField(max_length=64, blank=True, default="")
    branch_id = models.CharField(max_length=64, blank=True, default="")

    # Agregación.
    occurrence_count = models.PositiveIntegerField(default=1)
    first_seen_at = models.DateTimeField(default=timezone.now, editable=False)
    last_seen_at = models.DateTimeField(default=timezone.now)

    # Ciclo de triage.
    status = models.CharField(
        max_length=16, choices=ErrorStatus.choices, default=ErrorStatus.OPEN
    )
    owner = models.CharField(max_length=128, blank=True, default="")

    def __str__(self) -> str:
        return (
            f"ErrorEvent(domain={self.domain}, risk={self.risk_class}, "
            f"type={self.exception_type}, n={self.occurrence_count})"
        )
