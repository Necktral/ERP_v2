"""
Tests del módulo cec — control plane de cierres (close runs / excepciones).

Modelo: máquina de estados CloseRun.can_transition_to. Servicios: reglas de
bloqueo (_is_close_run_blocking), hashes deterministas, advance_close_run_state,
registro idempotente de excepciones, consistency score y execute_close_run sobre
una company sin datos (camino feliz → PACKAGED, score 100, outbox publicado).
API: health, create y execute de close run.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.modulos.cec.models import CECException, CloseRun
from apps.modulos.cec.services import (
    _build_consistency_score,
    _fingerprint,
    _is_close_run_blocking,
    _json_hash,
    _register_exception,
    advance_close_run_state,
    execute_close_run,
)
from apps.modulos.common.api_exceptions import ConflictError
from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.integration.models import OutboxEvent
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()
UT = OrgUnit.UnitType
S = CloseRun.Status


def _mk_org():
    s = uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=UT.HOLDING, name=f"H_{s}")
    company = OrgUnit.objects.create(unit_type=UT.COMPANY, name=f"C_{s}", parent=holding)
    branch = OrgUnit.objects.create(unit_type=UT.BRANCH, name=f"B_{s}", parent=company)
    return company, branch


def _mk_run(company, branch, status=S.CREATED):
    return CloseRun.objects.create(company=company, branch=branch, run_type=CloseRun.RunType.DAILY, status=status)


def _window():
    end = timezone.now()
    return end - timedelta(days=1), end


# ---------------------------------------------------------------------------
# Modelo: máquina de estados
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_close_run_state_machine_transitions():
    company, branch = _mk_org()
    run = _mk_run(company, branch, status=S.CREATED)
    assert run.can_transition_to(S.GATHERED) is True
    assert run.can_transition_to(S.CREATED) is True  # mismo estado
    assert run.can_transition_to(S.DELIVERED) is False
    assert run.can_transition_to(S.PACKAGED) is False

    run.status = S.PACKAGED
    assert run.can_transition_to(S.DELIVERED) is True
    assert run.can_transition_to(S.REOPENED_EXCEPTION) is True
    assert run.can_transition_to(S.GATHERED) is False


# ---------------------------------------------------------------------------
# Servicios: lógica pura
# ---------------------------------------------------------------------------

def test_is_close_run_blocking_always_blocking_codes():
    for code in (
        "CASH_DIFFERENCE_NONZERO",
        "NEGATIVE_STOCK",
        "FISCAL_B_PRINT_FAILED",
        "FISCAL_B_CONTINGENCY_OPEN",
        "PROCUREMENT_STOCK_COST_INTEGRITY",
    ):
        assert _is_close_run_blocking(code=code, strict=False) is True
        assert _is_close_run_blocking(code=code, strict=True) is True


def test_is_close_run_blocking_strict_gated_codes():
    for code in (
        "DOC_NUMBER_GAP",
        "BILLING_CASH_MISMATCH",
        "FISCAL_B_RESERVED_STALE",
        "PROCUREMENT_DOC_NUMBER_GAP",
        "PROCUREMENT_SUPPLIER_PAYMENT_MISMATCH",
    ):
        assert _is_close_run_blocking(code=code, strict=True) is True
        assert _is_close_run_blocking(code=code, strict=False) is False


def test_is_close_run_blocking_unknown_code_not_blocking():
    assert _is_close_run_blocking(code="SOMETHING_ELSE", strict=True) is False


def test_json_hash_is_order_independent_and_distinct():
    h1 = _json_hash({"a": 1, "b": 2})
    h2 = _json_hash({"b": 2, "a": 1})
    assert h1 == h2
    assert h1 != _json_hash({"a": 1, "b": 3})


def test_fingerprint_is_deterministic():
    args = dict(run_id="r1", code="NEGATIVE_STOCK", related_object_type="STOCK_BALANCE", related_object_id="7")
    assert _fingerprint(**args) == _fingerprint(**args)
    assert _fingerprint(**args) != _fingerprint(**{**args, "related_object_id": "8"})


# ---------------------------------------------------------------------------
# Servicios: advance / register / score
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_advance_close_run_state_valid_and_invalid():
    company, branch = _mk_org()
    run = _mk_run(company, branch, status=S.CREATED)
    advance_close_run_state(run=run, target_status=S.GATHERED)
    assert run.status == S.GATHERED

    with pytest.raises(ConflictError):
        advance_close_run_state(run=run, target_status=S.DELIVERED)


@pytest.mark.django_db
def test_advance_to_delivered_sets_completed_at():
    company, branch = _mk_org()
    run = _mk_run(company, branch, status=S.PACKAGED)
    advance_close_run_state(run=run, target_status=S.DELIVERED)
    assert run.status == S.DELIVERED
    assert run.completed_at is not None


@pytest.mark.django_db
def test_register_exception_creates_and_is_idempotent():
    company, branch = _mk_org()
    run = _mk_run(company, branch)
    kwargs = dict(
        run=run,
        code="NEGATIVE_STOCK",
        strict=True,
        related_object_type="STOCK_BALANCE",
        related_object_id="1",
        details_json={"qty": "-1"},
    )
    ex1, created1 = _register_exception(severity=CECException.Severity.CRITICAL, **kwargs)
    assert created1 is True
    assert ex1.is_blocking is True

    # Mismo fingerprint y excepción abierta => no crea otra, actualiza severidad.
    ex2, created2 = _register_exception(severity=CECException.Severity.HIGH, **kwargs)
    assert created2 is False
    assert ex2.id == ex1.id
    ex2.refresh_from_db()
    assert ex2.severity == CECException.Severity.HIGH
    assert CECException.objects.filter(close_run=run).count() == 1


@pytest.mark.django_db
def test_build_consistency_score_subtracts_weights():
    company, branch = _mk_org()
    run = _mk_run(company, branch)
    CECException.objects.create(
        source_module="CEC", code="X", severity=CECException.Severity.CRITICAL,
        status=CECException.Status.OPEN, company=company, branch=branch, close_run=run,
    )
    CECException.objects.create(
        source_module="CEC", code="Y", severity=CECException.Severity.MEDIUM,
        status=CECException.Status.OPEN, company=company, branch=branch, close_run=run,
    )
    # 100 - 40 (CRITICAL) - 10 (MEDIUM) = 50
    assert _build_consistency_score(run=run) == 50


# ---------------------------------------------------------------------------
# Servicios: execute_close_run
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_execute_close_run_clean_window_is_packaged():
    company, branch = _mk_org()
    run = _mk_run(company, branch, status=S.CREATED)
    ws, we = _window()
    result = execute_close_run(run=run, request=None, actor=None, window_start=ws, window_end=we, strict=True)

    assert result.status == S.PACKAGED
    assert result.consistency_score == 100
    assert result.blocking_exceptions_count == 0
    assert result.exceptions_opened_count == 0
    run.refresh_from_db()
    assert run.status == S.PACKAGED
    # Eventos de outbox publicados por el cierre.
    event_types = set(
        OutboxEvent.objects.filter(source_module="CEC").values_list("event_type", flat=True)
    )
    assert {"CloseRunExecuted", "CloseRunPackaged"} <= event_types


@pytest.mark.django_db
def test_execute_close_run_invalid_window_raises():
    company, branch = _mk_org()
    run = _mk_run(company, branch, status=S.CREATED)
    now = timezone.now()
    with pytest.raises(ValueError):
        execute_close_run(run=run, request=None, actor=None, window_start=now, window_end=now, strict=True)


@pytest.mark.django_db
def test_execute_close_run_from_wrong_status_raises():
    company, branch = _mk_org()
    run = _mk_run(company, branch, status=S.VALIDATED)
    ws, we = _window()
    with pytest.raises(ConflictError):
        execute_close_run(run=run, request=None, actor=None, window_start=ws, window_end=we, strict=True)


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def _client_with_perms(*, company, branch, perm_codes):
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
    login = client.post("/api/auth/login/", {"username": username, "password": "pass12345"}, format="json")
    assert login.status_code == 200, login.data
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data.get('access')}")
    client.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    client.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    return client


@pytest.mark.django_db
def test_cec_health_is_public():
    assert APIClient().get("/api/cec/health/").status_code == 200


@pytest.mark.django_db
def test_close_run_create_and_execute_via_api():
    company, branch = _mk_org()
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["cec.close_run.create", "cec.close_run.update", "cec.close_run.read"],
    )
    created = client.post("/api/cec/close-runs/", {"run_type": "DAILY"}, format="json")
    assert created.status_code == 201, created.data
    run_id = created.data["run_id"]

    ws, we = _window()
    executed = client.post(
        f"/api/cec/close-runs/{run_id}/execute/",
        {"window_start": ws.isoformat(), "window_end": we.isoformat(), "strict": True},
        format="json",
    )
    assert executed.status_code == 200, executed.data
    assert executed.data["status"] == S.PACKAGED
    assert executed.data["consistency_score"] == 100
