"""Tests de la rebanada B-1: ledger `ErrorEvent` (captura + dedupe + clasificación + API).

Los tests DETECTAN bugs (no pintan verde): cubren los invariantes J1 (correlación +
dominio + riesgo), J2 (redacción), J5 (dedupe por stack_hash) y el best-effort de la
captura (no rompe el request).
"""
from __future__ import annotations

import sys
import uuid
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.core.signals import got_request_exception
from rest_framework.test import APIClient

from apps.modulos.diagnostics.capture import capture_request_exception
from apps.modulos.diagnostics.domain_map import domain_for_path, risk_class_for_domain
from apps.modulos.diagnostics.extract import scrub_secrets
from apps.modulos.diagnostics.models import ErrorEvent
from apps.modulos.diagnostics.services import record_error_event
from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()


def _capture(msg: str, request=None) -> ErrorEvent:
    try:
        raise ValueError(msg)
    except ValueError:
        exc_type, exc_value, tb = sys.exc_info()
        assert exc_type is not None  # dentro de except: nunca None
        return record_error_event(
            exc_type=exc_type, exc_value=exc_value, tb=tb, request=request
        )


# --- Unidad pura (sin DB) -------------------------------------------------------

def test_domain_and_risk_classification():
    assert domain_for_path("backend/src/apps/kernels/payments/services.py") == "payments"
    assert risk_class_for_domain("payments") == "C1"
    assert domain_for_path("/app/backend/src/apps/kernels/reporting/contracts.py") == "reporting"
    assert risk_class_for_domain("reporting") == "C2"
    assert domain_for_path("backend/src/apps/modulos/documents/views.py") == "documents"
    assert risk_class_for_domain("documents") == "C3"
    assert risk_class_for_domain("unknown") == "C3"


def test_scrub_secrets_redacts_key_value():
    out = scrub_secrets("Authorization: Bearer abc.def y token=xyz123")
    assert "abc.def" not in out
    assert "xyz123" not in out
    assert "***REDACTED***" in out


def test_capture_is_best_effort(monkeypatch):
    # Si la persistencia falla, el receiver NO debe propagar (no rompe el request).
    from apps.modulos.diagnostics import services as svc

    def _boom(**kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(svc, "record_error_event", _boom)
    try:
        raise ValueError("x")
    except ValueError:
        capture_request_exception(sender=None, request=None)  # no debe lanzar


# --- Persistencia (con DB) ------------------------------------------------------

@pytest.mark.django_db
def test_dedupe_by_stack_hash_increments_occurrence():
    # Ambas capturas desde la MISMA línea (comprehension) → mismo stack_hash → dedupe.
    events = [_capture("boom") for _ in range(2)]
    assert events[0].error_id == events[1].error_id
    assert ErrorEvent.objects.count() == 1
    assert ErrorEvent.objects.get(error_id=events[0].error_id).occurrence_count == 2


@pytest.mark.django_db
def test_correlation_and_context_from_request():
    req = SimpleNamespace(
        request_id="corr-abc-123", path="/api/x/", method="POST", company=None, branch=None
    )
    ev = _capture("err", request=req)
    assert ev.correlation_id == "corr-abc-123"
    assert ev.endpoint == "/api/x/"
    assert ev.method == "POST"
    assert ev.domain == "diagnostics"  # el frame top vive en este módulo de tests
    assert ev.risk_class == "C2"  # calibración: la plataforma de diagnóstico es C2


@pytest.mark.django_db
def test_message_is_hashed_not_stored_raw():
    ev = _capture("password=hunter2secret")
    assert len(ev.message_hash) == 64  # mensaje hasheado
    assert "hunter2secret" not in ev.stack_trace_redacted  # nunca crudo en la traza


# --- Integración por señal got_request_exception --------------------------------

@pytest.mark.django_db
def test_signal_receiver_records_event_on_got_request_exception():
    # Enviar la señal dentro de un contexto de excepción ejercita el receiver REAL
    # (conectado en apps.ready) sin la maquinaria de 500 del test-client.
    req = SimpleNamespace(
        request_id="corrtest12345", path="/boom/", method="GET", company=None, branch=None
    )
    try:
        raise ValueError("boom password=topsecret123")
    except ValueError:
        got_request_exception.send(sender=None, request=req)

    ev = ErrorEvent.objects.get(correlation_id="corrtest12345")
    assert ev.exception_type == "ValueError"
    assert ev.domain == "diagnostics"  # el frame top vive en este módulo
    assert "topsecret123" not in ev.stack_trace_redacted  # secreto del fuente, scrubbeado


# --- API de lectura (RBAC) ------------------------------------------------------

def _mk_scope() -> tuple[OrgUnit, OrgUnit]:
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding
    )
    branch = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.BRANCH, name="B", parent=company
    )
    return company, branch


def _mk_client(*, company: OrgUnit, branch: OrgUnit, perm_codes: list[str]) -> APIClient:
    username = f"diag_{uuid.uuid4().hex[:8]}"
    user = User.objects.create_user(
        username=username, email=f"{username}@test.local", password="pass12345"
    )
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)
    role = Role.objects.create(name=f"diag_role_{uuid.uuid4().hex[:8]}", is_active=True)
    for code in perm_codes:
        perm, _ = Permission.objects.get_or_create(
            code=code, defaults={"description": code, "is_active": True}
        )
        RolePermission.objects.get_or_create(role=role, permission=perm)
    RoleAssignment.objects.create(user=user, role=role, org_unit=company, is_active=True)
    RoleAssignment.objects.create(user=user, role=role, org_unit=branch, is_active=True)
    client = APIClient()
    login = client.post(
        "/api/auth/login/", {"username": username, "password": "pass12345"}, format="json"
    )
    assert login.status_code == 200, login.data
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    client.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    client.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    return client


@pytest.mark.django_db
def test_error_list_requires_permission():
    r = APIClient().get("/api/diagnostics/errors/")
    assert r.status_code in (401, 403)


@pytest.mark.django_db
def test_error_list_ok_with_permission():
    company, branch = _mk_scope()
    client = _mk_client(company=company, branch=branch, perm_codes=["diagnostics.error.read"])
    r = client.get("/api/diagnostics/errors/")
    assert r.status_code == 200, r.data
    assert "results" in r.data


@pytest.mark.django_db
def test_seed_grants_diagnostics_read_to_company_admin():
    from apps.modulos.rbac.seed_v01 import seed_rbac_v01

    seed_rbac_v01()
    role = Role.objects.get(name="company_admin")
    codes = set(
        RolePermission.objects.filter(role=role).values_list("permission__code", flat=True)
    )
    assert "diagnostics.error.read" in codes
