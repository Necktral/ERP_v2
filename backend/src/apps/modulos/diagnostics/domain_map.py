"""Fuente única **path→dominio** y **dominio→clase de riesgo** (Necktral C1/C2/C3).

No se importa `qa/` desde la app; se replica el concepto `DomainScope` de
`qa/coverage_by_domain_guard.py` mapeando el segmento de módulo (`apps/kernels/<x>` o
`apps/modulos/<x>`) a un dominio — robusto a rutas absolutas o relativas. Es la base que
las rebanadas siguientes (SecurityFinding, CodeUnitEvidence) reutilizarán.

Calibración: cada módulo real del repo está clasificado EXPLÍCITAMENTE en C1/C2/C3
(el test centinela lo exige); `unknown`/no listado cae a C3 solo como red de seguridad.
La definición C1 es la de Necktral: dinero/stock/fiscal/permisos/CEC/auditoría — por
eso `rbac` y `accounts` (permisos/identidad) son C1, no C3.
"""
from __future__ import annotations

import re

# C1: tocan dinero/stock/fiscal/permisos/CEC/auditoría.
_C1_DOMAINS = frozenset(
    {
        # Dinero / fiscal.
        "payments",
        "facturacion",
        "accounting",
        "nomina",
        "portfolio",
        "compras",  # genera cuentas por pagar y entradas de stock
        "retail_pos",  # ventas: dinero y stock
        "comisariato",  # tienda a crédito ligada a planilla: dinero
        "intercompany",  # cruces facturados entre RUCs: fiscal
        # Stock.
        "inventarios",
        "estacion_servicios",  # control de combustible: stock sensible a fraude
        # Permisos / identidad.
        "iam",
        "rbac",  # el sistema de permisos mismo
        "accounts",  # login/2FA: comprometer auth = comprometer permisos
        # Control interno.
        "cec",
        "audit",
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
        "org",  # estructura multi-empresa (la imposición de límites vive en iam/rbac)
        "hr",  # alimenta nómina pero no postea dinero
        "finca",  # captura operacional que alimenta costos
        "parties",  # espina económica de identidad
        "fleet",
        "activity",  # telemetría de uso/sesiones (la auditoría de seguridad es `audit`)
        "common",  # infraestructura compartida (permissions escala a iam por override)
        "diagnostics",  # esta plataforma: si falla, la captura calla
    }
)
# C3 EXPLÍCITO: baja exposición, decidido — no "se nos olvidó clasificarlo".
_C3_DOMAINS = frozenset(
    {
        "documents",
        "notifications",
    }
)

# Overrides por path: sub-árboles cuyo riesgo NO es el del módulo contenedor.
# Caso canónico: la IMPOSICIÓN de permisos (DRF) vive en common/ pero es dominio iam.
_PATH_OVERRIDES: tuple[tuple[str, str], ...] = (
    ("apps/modulos/common/permissions", "iam"),
)

_MODULE_RE = re.compile(r"apps/(?:kernels|modulos)/([a-z_]+)")


def classified_domains() -> frozenset[str]:
    """Catálogo completo de dominios clasificados (para el test centinela)."""
    return _C1_DOMAINS | _C2_DOMAINS | _C3_DOMAINS


def domain_for_path(file_path: str) -> str:
    """Dominio del path (módulo más profundo); `platform` para config/, `unknown` si no aplica."""
    normalized = (file_path or "").replace("\\", "/")
    for prefix, domain in _PATH_OVERRIDES:
        if prefix in normalized:
            return domain
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
