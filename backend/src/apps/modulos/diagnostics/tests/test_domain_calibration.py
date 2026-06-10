"""Calibración del mapa dominio→riesgo (la definición C1 de Necktral, aplicada de verdad).

Fija las promociones que salieron de la auditoría: `rbac`/`accounts` son **permisos**
(C1 por definición), `intercompany` es fiscal, `compras`/`retail_pos`/`comisariato`
son dinero, `estacion_servicios` es stock sensible a fraude. El test centinela exige
que cada módulo real del repo esté clasificado explícitamente: un módulo nuevo sin
clasificar rompe el test en vez de caer en silencio a C3.
"""
from __future__ import annotations

from pathlib import Path

from apps.modulos.diagnostics.domain_map import (
    classified_domains,
    domain_for_path,
    risk_class_for_domain,
)

_APPS_ROOT = Path(__file__).resolve().parents[3]


def test_permisos_e_identidad_son_c1():
    # La definición C1 dice "permisos": el sistema de permisos y el login lo son.
    assert risk_class_for_domain("rbac") == "C1"
    assert risk_class_for_domain("accounts") == "C1"
    assert risk_class_for_domain("iam") == "C1"


def test_dinero_fiscal_y_stock_son_c1():
    assert risk_class_for_domain("intercompany") == "C1"  # cruces facturados entre RUCs
    assert risk_class_for_domain("compras") == "C1"
    assert risk_class_for_domain("retail_pos") == "C1"
    assert risk_class_for_domain("comisariato") == "C1"
    assert risk_class_for_domain("estacion_servicios") == "C1"  # combustible = stock


def test_operacional_y_espina_son_c2():
    for domain in ("hr", "finca", "org", "parties", "fleet", "common", "activity", "diagnostics"):
        assert risk_class_for_domain(domain) == "C2", domain


def test_c3_solo_lo_decidido():
    assert risk_class_for_domain("documents") == "C3"
    assert risk_class_for_domain("notifications") == "C3"
    assert risk_class_for_domain("unknown") == "C3"  # red de seguridad


def test_override_la_imposicion_de_permisos_es_iam():
    # common/permissions.py implementa rbac_permission: su riesgo es el de iam, no el de common.
    path = "backend/src/apps/modulos/common/permissions.py"
    assert domain_for_path(path) == "iam"
    assert risk_class_for_domain(domain_for_path(path)) == "C1"
    # El resto de common sigue siendo common (C2).
    assert domain_for_path("backend/src/apps/modulos/common/pagination.py") == "common"


def test_centinela_todo_modulo_real_esta_clasificado():
    catalog = classified_domains()
    sin_clasificar: list[str] = []
    for bucket in ("modulos", "kernels"):
        root = _APPS_ROOT / bucket
        if not root.is_dir():
            continue
        for child in sorted(root.iterdir()):
            if not child.is_dir() or child.name.startswith("__"):
                continue
            if child.name not in catalog:
                sin_clasificar.append(f"{bucket}/{child.name}")
    assert not sin_clasificar, (
        "Módulos sin clase de riesgo explícita en domain_map (decidir C1/C2/C3, "
        f"no dejar caer a C3 en silencio): {sin_clasificar}"
    )
