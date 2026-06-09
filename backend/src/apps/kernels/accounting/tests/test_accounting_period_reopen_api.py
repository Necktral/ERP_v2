"""Tests de endpoint de reapertura de periodo fiscal (Unidad #4, endurecimiento).

Cubre POST /api/accounting/periods/reopen/ end-to-end: RBAC (accounting.period.reopen),
gate de override SoD (force/allow_same_closer exigen accounting.sod.override),
guarda cronológica (409) y emisión de auditoría #4.
"""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.kernels.accounting.models import FiscalPeriod
from apps.modulos.audit.models import AuditEvent
from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()


def _mk_org():
    s = uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H_{s}")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name=f"C_{s}", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name=f"B_{s}", parent=company)
    return company, branch


def _client_with_perms(*, company: OrgUnit, branch: OrgUnit, perm_codes: list[str]) -> APIClient:
    username = f"api_{uuid.uuid4().hex[:8]}"
    user = User.objects.create_user(username=username, email=f"{username}@test.local", password="pass12345")
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)
    role = Role.objects.create(name=f"role_{uuid.uuid4().hex[:8]}", is_active=True)
    for code in perm_codes:
        perm, _ = Permission.objects.get_or_create(code=code, defaults={"description": code, "is_active": True})
        RolePermission.objects.get_or_create(role=role, permission=perm)
    RoleAssignment.objects.create(user=user, role=role, org_unit=company, is_active=True)
    RoleAssignment.objects.create(user=user, role=role, org_unit=branch, is_active=True)

    client = APIClient()
    r = client.post("/api/auth/login/", {"username": user.username, "password": "pass12345"}, format="json")
    assert r.status_code == 200
    access = r.data.get("access") if isinstance(r.data, dict) else None
    if isinstance(access, str) and access:
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    client.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    client.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    return client


@pytest.mark.django_db
def test_reopen_endpoint_happy_path_emits_audit():
    company, branch = _mk_org()
    period = FiscalPeriod.objects.create(company=company, year=2026, month=1, status=FiscalPeriod.Status.CLOSED)
    client = _client_with_perms(company=company, branch=branch, perm_codes=["accounting.period.reopen"])

    r = client.post("/api/accounting/periods/reopen/", {"year": 2026, "month": 1, "reason": "reproceso"}, format="json")

    assert r.status_code == 200, r.data
    assert r.data["status"] == FiscalPeriod.Status.OPEN
    assert r.data["was_already_open"] is False
    period.refresh_from_db()
    assert period.status == FiscalPeriod.Status.OPEN
    assert AuditEvent.objects.filter(event_type="ACCOUNTING_PERIOD_REOPENED", subject_id=str(period.id)).exists()


@pytest.mark.django_db
def test_reopen_endpoint_requires_permission():
    company, branch = _mk_org()
    FiscalPeriod.objects.create(company=company, year=2026, month=2, status=FiscalPeriod.Status.CLOSED)
    client = _client_with_perms(company=company, branch=branch, perm_codes=["accounting.period.read"])

    r = client.post("/api/accounting/periods/reopen/", {"year": 2026, "month": 2, "reason": "x"}, format="json")

    assert r.status_code == 403


@pytest.mark.django_db
def test_reopen_endpoint_force_requires_sod_override():
    company, branch = _mk_org()
    FiscalPeriod.objects.create(company=company, year=2026, month=3, status=FiscalPeriod.Status.CLOSED)
    # Tiene reopen pero NO sod.override -> force debe ser rechazado con 403.
    client = _client_with_perms(company=company, branch=branch, perm_codes=["accounting.period.reopen"])

    r = client.post(
        "/api/accounting/periods/reopen/",
        {"year": 2026, "month": 3, "reason": "x", "force": True},
        format="json",
    )

    assert r.status_code == 403
    assert "accounting.sod.override" in str(r.data)


@pytest.mark.django_db
def test_reopen_endpoint_chronological_guard_conflict():
    company, branch = _mk_org()
    FiscalPeriod.objects.create(company=company, year=2026, month=4, status=FiscalPeriod.Status.CLOSED)
    FiscalPeriod.objects.create(company=company, year=2026, month=5, status=FiscalPeriod.Status.CLOSED)
    client = _client_with_perms(company=company, branch=branch, perm_codes=["accounting.period.reopen"])

    # Reabrir abril con mayo cerrado, sin force -> 409 (guarda cronológica).
    r = client.post("/api/accounting/periods/reopen/", {"year": 2026, "month": 4, "reason": "x"}, format="json")

    assert r.status_code == 409
