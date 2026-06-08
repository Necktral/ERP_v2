"""Tests del control plane anti-fraude (Capa 3).

Matriz SoD + detectores (concesión/ejercicio) + hallazgos + endpoints con RBAC.
"""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework.test import APIClient

from apps.modulos.audit.models import AuditEvent
from apps.modulos.controls.models import ControlFinding, SegregationRule
from apps.modulos.controls.services import (
    detect_exercised_segregation,
    evaluate_user_segregation,
    materialize_findings,
    scan_company_segregation,
)
from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()
UT = OrgUnit.UnitType


def _mk_org():
    s = uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=UT.HOLDING, name=f"H_{s}")
    company = OrgUnit.objects.create(unit_type=UT.COMPANY, name=f"C_{s}", parent=holding)
    branch = OrgUnit.objects.create(unit_type=UT.BRANCH, name=f"B_{s}", parent=company)
    return holding, company, branch


def _mk_user(prefix="u"):
    username = f"{prefix}_{uuid.uuid4().hex[:8]}"
    return User.objects.create_user(username=username, email=f"{username}@test.local", password="pass12345")


def _grant_perms(user, company, branch, perm_codes):
    UserMembership.objects.get_or_create(user=user, org_unit=company, defaults={"is_active": True})
    UserMembership.objects.get_or_create(user=user, org_unit=branch, defaults={"is_active": True})
    role = Role.objects.create(name=f"role_{uuid.uuid4().hex[:8]}", is_active=True)
    for code in perm_codes:
        perm, _ = Permission.objects.get_or_create(code=code, defaults={"description": code, "is_active": True})
        RolePermission.objects.get_or_create(role=role, permission=perm)
    RoleAssignment.objects.create(user=user, role=role, org_unit=company, is_active=True)
    RoleAssignment.objects.create(user=user, role=role, org_unit=branch, is_active=True)
    return user


def _client(user, company, branch):
    c = APIClient()
    login = c.post("/api/auth/login/", {"username": user.username, "password": "pass12345"}, format="json")
    assert login.status_code == 200, login.data
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data.get('access')}")
    c.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    c.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    return c


def _audit(company, event_type, actor, module="TEST"):
    return AuditEvent.objects.create(
        event_type=event_type,
        module=module,
        timestamp_server=timezone.now(),
        partition_key=f"COMPANY:{company.id}",
        actor_user=actor,
    )


# ---------------------------------------------------------------------------
# Catálogo / modelo
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_global_rules_seeded():
    codes = set(SegregationRule.objects.filter(company__isnull=True, is_active=True).values_list("code", flat=True))
    assert {"ghost_employee", "invoice_create_void", "self_grant_power"} <= codes


@pytest.mark.django_db
def test_rule_clean_rejects_non_company():
    _, _, branch = _mk_org()
    rule = SegregationRule(company=branch, code="x", name="x", permission_a="a.b", permission_b="c.d")
    with pytest.raises(ValidationError):
        rule.full_clean()


# ---------------------------------------------------------------------------
# Detector por concesión (SOD_GRANT)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_evaluate_and_scan_grant_violation():
    _, company, branch = _mk_org()
    bad = _mk_user("bad")
    _grant_perms(bad, company, branch, ["hr.employee.create", "nomina.period.approve"])
    good = _mk_user("good")
    _grant_perms(good, company, branch, ["hr.employee.create"])

    violated = {r.code for r in evaluate_user_segregation(bad, company)}
    assert "ghost_employee" in violated
    assert evaluate_user_segregation(good, company) == []

    items = scan_company_segregation(company)
    grant = {(i.actor_user_id, i.rule.code) for i in items}
    assert (bad.id, "ghost_employee") in grant
    assert (good.id, "ghost_employee") not in grant


# ---------------------------------------------------------------------------
# Detector por ejercicio (SOD_EXERCISED)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_detect_exercised_from_audit_log():
    _, company, _ = _mk_org()
    actor = _mk_user("act")
    _audit(company, "HR_EMPLOYEE_CREATED", actor)
    _audit(company, "NOMINA_PERIOD_APPROVED", actor)
    # otro actor solo hizo una de las dos -> no viola
    other = _mk_user("oth")
    _audit(company, "HR_EMPLOYEE_CREATED", other)

    items = detect_exercised_segregation(company, window_days=90)
    hits = {(i.actor_user_id, i.rule.code, i.control_code) for i in items}
    assert (actor.id, "ghost_employee", "SOD_EXERCISED") in hits
    assert not any(i.actor_user_id == other.id for i in items)


@pytest.mark.django_db
def test_materialize_is_idempotent():
    _, company, _ = _mk_org()
    actor = _mk_user("act")
    _audit(company, "HR_EMPLOYEE_CREATED", actor)
    _audit(company, "NOMINA_PERIOD_APPROVED", actor)
    items = detect_exercised_segregation(company, window_days=90)
    first = materialize_findings(company, items)
    assert len(first) >= 1
    second = materialize_findings(company, items)
    assert second == []
    assert ControlFinding.objects.filter(company=company).count() == len(first)


# ---------------------------------------------------------------------------
# HTTP + RBAC
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_rules_endpoint_requires_perm():
    _, company, branch = _mk_org()
    nope = _grant_perms(_mk_user("n"), company, branch, ["org.company.read"])
    r = _client(nope, company, branch).get("/api/controls/sod/rules/")
    assert r.status_code == 403


@pytest.mark.django_db
def test_scan_findings_resolve_flow():
    _, company, branch = _mk_org()
    officer = _grant_perms(
        _mk_user("off"),
        company,
        branch,
        ["controls.sod.read", "controls.findings.read", "controls.findings.manage"],
    )
    # un usuario con combo tóxico para que el scan encuentre algo
    bad = _mk_user("bad")
    _grant_perms(bad, company, branch, ["hr.employee.create", "nomina.period.approve"])

    api = _client(officer, company, branch)

    r = api.get("/api/controls/sod/rules/")
    assert r.status_code == 200 and len(r.data["results"]) >= 1

    r = api.post("/api/controls/scan/", {}, format="json")
    assert r.status_code == 200, r.data
    assert r.data["created"] >= 1

    r = api.get("/api/controls/findings/")
    assert r.status_code == 200
    assert r.data["count"] >= 1
    fid = r.data["results"][0]["id"]

    r = api.post(f"/api/controls/findings/{fid}/resolve/", {"status": "RESOLVED", "note": "ok"}, format="json")
    assert r.status_code == 200, r.data
    assert r.data["status"] == "RESOLVED"
    assert AuditEvent.objects.filter(event_type="CONTROL_FINDING_RESOLVED", subject_id=str(fid)).exists()

    # re-scan no duplica
    r2 = api.post("/api/controls/scan/", {}, format="json")
    assert r2.data["created"] == 0
