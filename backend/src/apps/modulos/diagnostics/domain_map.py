"""Fuente única **path→dominio** y **dominio→clase de riesgo** (Necktral C1/C2/C3).

No se importa `qa/` desde la app; se replica el concepto `DomainScope` de
`qa/coverage_by_domain_guard.py` mapeando el segmento de módulo (`apps/kernels/<x>` o
`apps/modulos/<x>`) a un dominio — robusto a rutas absolutas o relativas. Es la base que
las rebanadas siguientes (SecurityFinding, CodeUnitEvidence) reutilizarán.
"""
from __future__ import annotations

import re

# C1: tocan dinero/stock/fiscal/permisos/CEC/auditoría.
_C1_DOMAINS = frozenset(
    {
        "payments",
        "facturacion",
        "accounting",
        "inventarios",
        "iam",
        "cec",
        "audit",
        "nomina",
        "portfolio",
    }
)
# C2: confiabilidad/trazabilidad/API/reporting/sync.
_C2_DOMAINS = frozenset(
    {
        "reporting",
        "integration",
        "sync",
        "sync_engine",
        "dashboard",
        "controls",
    }
)

_MODULE_RE = re.compile(r"apps/(?:kernels|modulos)/([a-z_]+)")


def domain_for_path(file_path: str) -> str:
    """Dominio del path (módulo más profundo); `platform` para config/, `unknown` si no aplica."""
    normalized = (file_path or "").replace("\\", "/")
    matches = _MODULE_RE.findall(normalized)
    if matches:
        return matches[-1]
    if "config/" in normalized:
        return "platform"
    return "unknown"


def risk_class_for_domain(domain: str) -> str:
    """Traduce el dominio a la severidad Necktral C1/C2/C3."""
    if domain in _C1_DOMAINS:
        return "C1"
    if domain in _C2_DOMAINS or domain == "platform":
        return "C2"
    return "C3"
