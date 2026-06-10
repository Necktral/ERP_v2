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

from django.conf import settings
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


class FindingStatus(models.TextChoices):
    OPEN = "open", "Abierto"
    TRIAGED = "triaged", "Triado"
    CONFIRMED = "confirmed", "Confirmado"
    FIXED = "fixed", "Corregido (ya no aparece)"
    ACCEPTED_RISK = "accepted_risk", "Riesgo aceptado (excepción vigente)"
    FALSE_POSITIVE = "false_positive", "Falso positivo"


# Estados que la ingesta recalcula automáticamente; el resto son decisiones humanas
# que la re-ingesta NO debe pisar.
AUTO_FINDING_STATES = frozenset(
    {FindingStatus.OPEN, FindingStatus.ACCEPTED_RISK, FindingStatus.FIXED}
)


class SecurityFinding(models.Model):
    """Hallazgo de seguridad persistido (Mundo B, rebanada B-2).

    Convierte el JSON efímero de los scanners (pip-audit/npm-audit; SAST en una
    sub-rebanada siguiente) en un ledger consultable, deduplicado por
    (source_tool, package, vuln_id), consciente del contrato de excepciones con
    vencimiento (`qa/contracts/security_exceptions.json`). La IA no entra acá: la
    ingesta es determinista y respeta las decisiones humanas de triage.
    """

    class Meta:
        app_label = "diagnostics"
        ordering = ["-last_seen_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["source_tool", "package", "vuln_id"],
                name="uniq_securityfinding_natural_key",
            )
        ]
        indexes = [
            models.Index(fields=["source_tool", "status"]),
            models.Index(fields=["risk_class", "status"]),
            models.Index(fields=["status", "-last_seen_at"]),
        ]

    finding_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    # Identidad / origen.
    source_tool = models.CharField(max_length=32)  # "pip" | "npm" | "bandit" | ...
    vuln_id = models.CharField(max_length=128)  # CVE/GHSA/advisory/test id
    package = models.CharField(max_length=255, blank=True, default="")
    package_version = models.CharField(max_length=64, blank=True, default="")
    fixed_version = models.CharField(max_length=64, blank=True, default="")
    cve_id = models.CharField(max_length=64, blank=True, default="")
    cwe_id = models.CharField(max_length=32, blank=True, default="")

    # Ubicación (SAST; vacío para dependencias).
    file_path = models.CharField(max_length=512, blank=True, default="")
    line_start = models.PositiveIntegerField(default=0)
    symbol = models.CharField(max_length=255, blank=True, default="")
    domain = models.CharField(max_length=64, blank=True, default="")

    # Clasificación Necktral. `reachable=unknown` por defecto (no se automatiza).
    severity_raw = models.CharField(max_length=32, blank=True, default="")
    risk_class = models.CharField(
        max_length=2, choices=RiskClass.choices, default=RiskClass.C3
    )
    reachable = models.CharField(max_length=8, default="unknown")  # unknown|yes|no

    # Estado / excepción.
    status = models.CharField(
        max_length=16, choices=FindingStatus.choices, default=FindingStatus.OPEN
    )
    owner = models.CharField(max_length=128, blank=True, default="")
    accepted_risk_reason = models.CharField(max_length=255, blank=True, default="")
    expires_at = models.DateField(null=True, blank=True)

    first_seen_at = models.DateTimeField(default=timezone.now, editable=False)
    last_seen_at = models.DateTimeField(default=timezone.now)

    def __str__(self) -> str:
        return (
            f"SecurityFinding(tool={self.source_tool}, id={self.vuln_id}, "
            f"risk={self.risk_class}, status={self.status})"
        )


class AIControl(models.Model):
    """Botón de apagado runtime de la IA (singleton, pk=1).

    Combinado con el flag de entorno `AI_FEATURES_ENABLED` (apagado por defecto): la IA
    solo opera si el entorno la habilita **Y** este interruptor runtime está encendido.
    Cualquier funcionalidad de IA DEBE consultar `flags.ai_features_enabled()`. Permite
    apagar TODA la IA en caliente (sin redeploy) desde un admin con permiso.
    """

    SINGLETON_ID = 1

    class Meta:
        app_label = "diagnostics"

    ai_enabled = models.BooleanField(default=True)
    reason = models.CharField(max_length=255, blank=True, default="")
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ai_control_updates",
    )
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def current(cls) -> AIControl:
        obj, _ = cls.objects.get_or_create(pk=cls.SINGLETON_ID)
        return obj

    def save(self, *args: object, **kwargs: object) -> None:
        self.pk = self.SINGLETON_ID
        super().save(*args, **kwargs)  # type: ignore[arg-type]

    def __str__(self) -> str:
        return f"AIControl(ai_enabled={self.ai_enabled})"


class DiagnosisStatus(models.TextChoices):
    OPEN = "open", "Abierto"
    REVIEWED = "reviewed", "Revisado"
    ACCEPTED = "accepted", "Aceptado"
    DISMISSED = "dismissed", "Descartado"


class DiagnosticRun(models.Model):
    """Corrida de diagnóstico de **causa raíz** sobre un fallo (Mundo B).

    El paquete de evidencia (`evidence`) es **DETERMINISTA, sin IA**: explica el *por qué*
    de un fallo cruzando su contexto, timeline y señales relacionadas. La hipótesis de
    causa (`root_cause_hypothesis`) la completa un humano o, en el futuro y **solo si el
    kill switch lo permite** (`flags.ai_features_enabled()`), el motor IA advisory.
    """

    class Meta:
        app_label = "diagnostics"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["subject_type", "subject_id"]),
            models.Index(fields=["risk_class", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
        ]

    run_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    # Sujeto (polimórfico, desacoplado: hoy un ErrorEvent; mañana un SecurityFinding).
    subject_type = models.CharField(max_length=32, default="error_event")
    subject_id = models.CharField(max_length=64)

    trigger_type = models.CharField(max_length=16, default="manual")  # manual|runtime|scheduled
    domain = models.CharField(max_length=64, blank=True, default="")
    risk_class = models.CharField(
        max_length=2, choices=RiskClass.choices, default=RiskClass.C3
    )

    # Evidencia DETERMINISTA (el "por qué", sin IA).
    evidence = models.JSONField(default=dict, blank=True)
    summary = models.TextField(blank=True, default="")
    blast_radius = models.JSONField(default=dict, blank=True)

    # Hipótesis / recomendaciones (humano o IA advisory; vacío por defecto).
    root_cause_hypothesis = models.TextField(blank=True, default="")
    recommended_tests = models.TextField(blank=True, default="")
    recommended_fix = models.TextField(blank=True, default="")
    confidence = models.CharField(max_length=8, blank=True, default="")  # low|medium|high

    ai_assisted = models.BooleanField(default=False)
    generated_by = models.CharField(max_length=16, default="deterministic")

    status = models.CharField(
        max_length=16, choices=DiagnosisStatus.choices, default=DiagnosisStatus.OPEN
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="diagnostic_reviews",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="diagnostic_runs",
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return (
            f"DiagnosticRun(subject={self.subject_type}:{self.subject_id}, "
            f"risk={self.risk_class}, ai={self.ai_assisted})"
        )
