"""Triage humano del ledger (ErrorEvent / SecurityFinding) — transiciones validadas.

La frase rectora del IA2 dice "el humano decide excepciones"; esta es la herramienta
para decidir: confirmar, descartar como falso positivo, marcar corregido o (solo
errores) aceptar el riesgo. La máquina valida que la transición sea legal y deja
rastro de QUIÉN decidió (`owner`). La automática respeta estas decisiones:

- Findings: la re-ingesta solo recalcula estados de `AUTO_FINDING_STATES`; un humano
  que confirma/descarta queda sticky. `accepted_risk` NO se puede fijar por API: esa
  decisión vive en el contrato de excepciones CON VENCIMIENTO
  (`qa/contracts/security_exceptions.json`) — la API no permite saltárselo.
- Errores: el centinela de regresión solo toca FIXED→REGRESSED; si un humano marca
  `fixed` y el fallo reaparece, vuelve a REGRESSED (no se puede mentir al ledger).
"""
from __future__ import annotations

from django.utils import timezone

from .models import ErrorEvent, ErrorStatus, FindingStatus, SecurityFinding


class TriageError(ValueError):
    """Transición de triage ilegal (estado destino no permitido para humanos)."""


# Estados que un humano puede FIJAR vía API. OPEN/REGRESSED son de la máquina;
# accepted_risk de findings es del contrato de excepciones (con vencimiento).
ERROR_HUMAN_TARGETS = frozenset(
    {
        ErrorStatus.TRIAGED.value,
        ErrorStatus.CONFIRMED.value,
        ErrorStatus.FIXED.value,
        ErrorStatus.ACCEPTED_RISK.value,
        ErrorStatus.FALSE_POSITIVE.value,
    }
)
FINDING_HUMAN_TARGETS = frozenset(
    {
        FindingStatus.TRIAGED.value,
        FindingStatus.CONFIRMED.value,
        FindingStatus.FIXED.value,
        FindingStatus.FALSE_POSITIVE.value,
    }
)


def triage_error(*, error: ErrorEvent, status: str, owner: str) -> ErrorEvent:
    if status not in ERROR_HUMAN_TARGETS:
        raise TriageError(
            f"Estado '{status}' no es fijable por triage humano "
            f"(permitidos: {sorted(ERROR_HUMAN_TARGETS)})."
        )
    error.status = status
    error.owner = owner[:128]
    error.last_seen_at = error.last_seen_at or timezone.now()
    error.save(update_fields=["status", "owner"])
    return error


def triage_finding(*, finding: SecurityFinding, status: str, owner: str) -> SecurityFinding:
    if status not in FINDING_HUMAN_TARGETS:
        raise TriageError(
            f"Estado '{status}' no es fijable por triage humano "
            f"(permitidos: {sorted(FINDING_HUMAN_TARGETS)}; 'accepted_risk' va por el "
            "contrato de excepciones con vencimiento, no por API)."
        )
    finding.status = status
    finding.owner = owner[:128]
    finding.save(update_fields=["status", "owner"])
    return finding
