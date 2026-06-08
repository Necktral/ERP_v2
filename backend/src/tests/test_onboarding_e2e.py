"""Smoke e2e del onboarding self-service.

Demuestra el principio del producto: cualquier usuario, desde un sistema fresco,
construye su empresa por API — admin inicial → holding/empresa/sucursal →
finca → cargo → empleado → asignación → provisión de acceso → configuración de
nómina → elección de módulos. Cada paso se asierta; si la cadena se rompe, este
test lo revela (es el contrato de onboarding de punta a punta).
"""
from __future__ import annotations

import pytest
from rest_framework.test import APIClient

OWNER_PASS = "OwnerPass123!"


@pytest.mark.django_db
def test_onboarding_e2e_self_service():
    api = APIClient()

    # 1) Sistema fresco
    r = api.get("/api/auth/bootstrap/status/")
    assert r.status_code == 200, r.data
    assert r.data["is_fresh"] is True
    assert r.data["setup_required"] is True

    # 2) Primer admin (superuser)
    r = api.post(
        "/api/auth/bootstrap/init/",
        {"username": "owner", "password": OWNER_PASS, "email": "owner@acme.test"},
        format="json",
    )
    assert r.status_code == 201, r.data

    # 3) Login
    r = api.post("/api/auth/login/", {"username": "owner", "password": OWNER_PASS}, format="json")
    assert r.status_code == 200, r.data
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['access']}")

    # 4) Estructura inicial: holding → empresa → sucursal (+ RBAC + company_admin)
    r = api.post(
        "/api/auth/bootstrap/org/",
        {
            "holding_name": "ACME Holding",
            "company_name": "ACME S.A.",
            "company_tax_id": "J0310000000000",
            "branch_name": "Casa Matriz",
            "branch_address": "Managua",
        },
        format="json",
    )
    assert r.status_code == 200, r.data
    company_id = r.data["company_id"]
    branch_id = r.data["branch_id"]
    api.defaults["HTTP_X_COMPANY_ID"] = str(company_id)
    api.defaults["HTTP_X_BRANCH_ID"] = str(branch_id)

    # 5) Otra sucursal (finca)
    r = api.post("/api/org/branches/", {"name": "Finca Santa Isabel", "code": "FSI"}, format="json")
    assert r.status_code == 201, r.data
    finca_id = r.data["id"]

    # 6) Cargo
    r = api.post("/api/hr/positions/", {"name": "Cortador", "code": "COR"}, format="json")
    assert r.status_code == 201, r.data
    position_id = r.data["id"]

    # 7) Empleado
    r = api.post(
        "/api/hr/employees/",
        {"first_name": "Juan", "last_name": "Pérez", "employee_code": "E001"},
        format="json",
    )
    assert r.status_code == 201, r.data
    employee_id = r.data["id"]

    # 8) Asignación: empleado → cargo → finca
    r = api.post(
        f"/api/hr/employees/{employee_id}/assignments/",
        {"position_id": position_id, "branch_id": finca_id},
        format="json",
    )
    assert r.status_code == 201, r.data

    # 9) Provisionar acceso (login al empleado) — exige asignación activa
    r = api.post(
        f"/api/hr/employees/{employee_id}/provision-user/",
        {"username": "jperez", "email": "jperez@acme.test"},
        format="json",
    )
    assert r.status_code == 201, r.data

    # 10) Configurar nómina
    r = api.post("/api/nomina/config/", {"fiscal_year": 2026}, format="json")
    assert r.status_code == 201, r.data

    # 11) Escoger módulos: activar Inventario (lo va a ocupar); Estación queda OFF
    r = api.get("/api/org/modules/")
    assert r.status_code == 200, r.data
    by_code = {row["code"]: row for row in r.data["results"]}
    assert by_code["payroll"]["is_enabled"] is True
    assert by_code["inventory"]["is_enabled"] is False

    r = api.put(
        "/api/org/modules/", {"modules": [{"code": "inventory", "is_enabled": True}]}, format="json"
    )
    assert r.status_code == 200, r.data

    # 12) La sesión refleja los módulos efectivos de la empresa construida
    r = api.get("/api/auth/bootstrap/session/")
    assert r.status_code == 200, r.data
    enabled = r.data["enabled_modules"]
    assert "payroll" in enabled
    assert "inventory" in enabled  # recién activado
    assert "fuel" not in enabled  # no lo ocupa
    # contexto resuelto a la empresa construida
    assert r.data["effective_context"]["company_id"] == str(company_id)
