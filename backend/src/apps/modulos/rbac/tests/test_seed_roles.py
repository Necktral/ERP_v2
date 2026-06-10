"""Roles predefinidos nuevos (plataforma/finanzas): fijan el diseño + el SoD.

Cada test afirma los permisos que el rol DEBE tener y, donde aplica, los sensibles que
NO debe tener (segregación de funciones). Detecta drift si alguien afloja un rol.
"""
from __future__ import annotations

import pytest

from apps.modulos.rbac.models import Role, RolePermission
from apps.modulos.rbac.seed_v01 import seed_rbac_v01


def _perms(role_name: str) -> set[str]:
    role = Role.objects.get(name=role_name)
    return set(
        RolePermission.objects.filter(role=role).values_list("permission__code", flat=True)
    )


@pytest.mark.django_db
def test_all_new_roles_exist():
    seed_rbac_v01()  # no debe disparar el hard-fail de permiso inexistente
    names = set(Role.objects.values_list("name", flat=True))
    assert {
        "platform_observer",
        "ai_steward",
        "accountant",
        "collections_officer",
        "viewer",
    } <= names


@pytest.mark.django_db
def test_platform_observer_diagnoses_but_does_not_govern_ai():
    seed_rbac_v01()
    p = _perms("platform_observer")
    assert {
        "diagnostics.error.read",
        "diagnostics.finding.read",
        "diagnostics.diagnose.read",
        "diagnostics.diagnose.run",
    } <= p
    # Segregado: NO gobierna la IA (eso es de ai_steward).
    assert "diagnostics.ai_control.manage" not in p
    assert "diagnostics.ai_diagnose.run" not in p


@pytest.mark.django_db
def test_ai_steward_governs_kill_switch():
    seed_rbac_v01()
    p = _perms("ai_steward")
    assert {
        "diagnostics.ai_control.read",
        "diagnostics.ai_control.manage",
        "diagnostics.ai_diagnose.run",
    } <= p


@pytest.mark.django_db
def test_accountant_has_sod_no_post_close_or_override():
    seed_rbac_v01()
    p = _perms("accountant")
    assert {
        "accounting.journal_draft.read",
        "accounting.journal_draft.approve",
        "accounting.report.read",
    } <= p
    # SoD: no postea, no cierra, no override (queda en company_admin/billing_manager).
    assert "accounting.journal_draft.post" not in p
    assert "accounting.period.close" not in p
    assert "accounting.sod.override" not in p


@pytest.mark.django_db
def test_collections_officer_no_writeoff_adjust_or_disburse():
    seed_rbac_v01()
    p = _perms("collections_officer")
    assert {"portfolio.receivable.read", "portfolio.allocation.write"} <= p
    assert "portfolio.receivable.writeoff" not in p
    assert "portfolio.receivable.adjust" not in p
    assert "portfolio.credit.disburse" not in p


@pytest.mark.django_db
def test_viewer_is_strictly_read_only():
    seed_rbac_v01()
    p = _perms("viewer")
    assert {"report.dashboard.read", "report.dataset.read", "audit.read"} <= p
    # Cero operaciones: ningún permiso de escritura/acción.
    write_suffixes = (
        ".write", ".create", ".update", ".manage", ".post", ".close",
        ".approve", ".void", ".issue", ".delete", ".disburse", ".writeoff", ".adjust",
    )
    assert not [c for c in p if c.endswith(write_suffixes)]
