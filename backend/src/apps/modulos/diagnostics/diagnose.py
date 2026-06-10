"""Motor de causa raíz DETERMINISTA (sin IA): el *por qué* de un fallo.

Cruza un `ErrorEvent` con su contexto, timeline y señales relacionadas para armar un
paquete de evidencia + un resumen legible — la cadena `síntoma → causa` del IA2, pero
sin IA. La hipótesis de causa la completa un humano o, en el futuro y SOLO si
`flags.ai_features_enabled()`, el motor IA advisory. La supervisión del *por qué*
funciona **siempre**, con la IA apagada.
"""
from __future__ import annotations

from typing import Any

from django.db.models import Q

from .models import DiagnosticRun, ErrorEvent, SecurityFinding

_RELATED_LIMIT = 10
_HIGH_OCCURRENCE = 5


def build_evidence_bundle(error: ErrorEvent) -> dict[str, Any]:
    """Paquete de evidencia determinista que explica el *por qué* del fallo."""
    related_errors = [
        {
            "error_id": str(r.error_id),
            "exception_type": r.exception_type,
            "file_path": r.file_path,
            "line_number": r.line_number,
            "occurrence_count": r.occurrence_count,
            "status": r.status,
        }
        for r in ErrorEvent.objects.filter(Q(domain=error.domain) | Q(file_path=error.file_path))
        .exclude(pk=error.pk)
        .order_by("-occurrence_count")[:_RELATED_LIMIT]
    ]
    related_findings: list[dict[str, Any]] = []
    if error.file_path:
        related_findings = [
            {
                "finding_id": str(f.finding_id),
                "source_tool": f.source_tool,
                "vuln_id": f.vuln_id,
                "risk_class": f.risk_class,
                "status": f.status,
            }
            for f in SecurityFinding.objects.filter(file_path=error.file_path).order_by(
                "-last_seen_at"
            )[:_RELATED_LIMIT]
        ]

    span_seconds = 0.0
    if error.last_seen_at and error.first_seen_at:
        span_seconds = (error.last_seen_at - error.first_seen_at).total_seconds()

    signals: list[str] = []
    if error.occurrence_count >= _HIGH_OCCURRENCE:
        signals.append("alta_frecuencia")
    if error.risk_class == "C1":
        signals.append("dominio_C1")
    if error.status == "regressed":
        signals.append("regresion")
    if not related_errors and not related_findings:
        signals.append("aislado")

    return {
        "error": {
            "error_id": str(error.error_id),
            "exception_type": error.exception_type,
            "file_path": error.file_path,
            "line_number": error.line_number,
            "function_name": error.function_name,
            "domain": error.domain,
            "risk_class": error.risk_class,
            "endpoint": error.endpoint,
            "method": error.method,
            "correlation_id": error.correlation_id,
        },
        "timeline": {
            "occurrence_count": error.occurrence_count,
            "first_seen_at": error.first_seen_at.isoformat() if error.first_seen_at else None,
            "last_seen_at": error.last_seen_at.isoformat() if error.last_seen_at else None,
            "span_seconds": span_seconds,
        },
        "related_errors": related_errors,
        "related_findings": related_findings,
        "signals": signals,
    }


def build_blast_radius(error: ErrorEvent) -> dict[str, Any]:
    return {
        "domain": error.domain,
        "endpoint": error.endpoint,
        "method": error.method,
        "risk_class": error.risk_class,
    }


def summarize(error: ErrorEvent, bundle: dict[str, Any]) -> str:
    """Resumen legible DETERMINISTA del *por qué* (sin IA)."""
    timeline = bundle["timeline"]
    n_rel = len(bundle["related_errors"])
    sig = ", ".join(bundle["signals"]) or "ninguna"
    loc = (
        f"{error.file_path}:{error.line_number} en {error.function_name}()"
        if error.file_path
        else "ubicación desconocida"
    )
    return (
        f"Fallo {error.exception_type} en dominio {error.domain or 'desconocido'} "
        f"(riesgo {error.risk_class}). {timeline['occurrence_count']} ocurrencia(s). "
        f"Ubicación: {loc}. Blast radius: {error.method or '—'} {error.endpoint or '—'}. "
        f"{n_rel} fallo(s) relacionado(s). Señales: {sig}. "
        f"Causa raíz: PENDIENTE (revisión humana; IA advisory solo con kill switch encendido)."
    )


def create_diagnostic_run(
    *, error: ErrorEvent, trigger_type: str = "manual", created_by: Any = None
) -> DiagnosticRun:
    """Crea una corrida de diagnóstico con evidencia determinista (sin IA)."""
    bundle = build_evidence_bundle(error)
    actor = created_by if (created_by and getattr(created_by, "is_authenticated", False)) else None
    return DiagnosticRun.objects.create(
        subject_type="error_event",
        subject_id=str(error.error_id),
        trigger_type=trigger_type,
        domain=error.domain,
        risk_class=error.risk_class,
        evidence=bundle,
        summary=summarize(error, bundle),
        blast_radius=build_blast_radius(error),
        generated_by="deterministic",
        ai_assisted=False,
        created_by=actor,
    )
