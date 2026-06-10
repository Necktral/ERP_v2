"""Gates de release DETERMINISTAS sobre el ledger (sin IA).

Frase rectora del IA2: *"la IA diagnostica con evidencia; los gates bloquean; el humano
decide excepciones."* Un **C1 abierto** (error de runtime o hallazgo de seguridad)
bloquea el release. Las **regresiones** se reportan (y, si son C1, ya bloquean por estar
abiertas). Evalúa el estado real del ledger; pensado para correr en el pipeline de deploy
(que tiene DB), no en el job de tests de CI.
"""
from __future__ import annotations

from typing import Any

from .models import ErrorEvent, ErrorStatus, FindingStatus, RiskClass, SecurityFinding

_OPEN_ERROR_STATES = [
    ErrorStatus.OPEN,
    ErrorStatus.TRIAGED,
    ErrorStatus.CONFIRMED,
    ErrorStatus.REGRESSED,
]
_OPEN_FINDING_STATES = [
    FindingStatus.OPEN,
    FindingStatus.TRIAGED,
    FindingStatus.CONFIRMED,
]


def evaluate_release_gates() -> dict[str, Any]:
    """Verdicto de release + conteos. `blocked=True` si hay C1 abierto."""
    c1_errors_open = ErrorEvent.objects.filter(
        risk_class=RiskClass.C1, status__in=_OPEN_ERROR_STATES
    ).count()
    c1_findings_open = SecurityFinding.objects.filter(
        risk_class=RiskClass.C1, status__in=_OPEN_FINDING_STATES
    ).count()
    regressions = ErrorEvent.objects.filter(status=ErrorStatus.REGRESSED).count()

    blockers: list[str] = []
    if c1_errors_open:
        blockers.append(f"{c1_errors_open} ErrorEvent C1 abierto(s)")
    if c1_findings_open:
        blockers.append(f"{c1_findings_open} SecurityFinding C1 abierto(s)")

    return {
        "blocked": bool(blockers),
        "blockers": blockers,
        "counts": {
            "c1_errors_open": c1_errors_open,
            "c1_findings_open": c1_findings_open,
            "regressions": regressions,
        },
    }
