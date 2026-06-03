"""
Tests del módulo common — utilidades transversales del backend.

Cubre: errores de dominio tipados, excepción API de conflicto, paginación
limit/offset, catálogo de medios de pago (tender), mixin de throttle por método,
el permiso DRF rbac_permission (sin DB, vía override e intercompany monkeypatched)
y el endpoint MetricsView (auth + staff).
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.modulos.common import tender as t
from apps.modulos.common.api_exceptions import ConflictError
from apps.modulos.common.domain_errors import (
    DomainError,
    IntegrationError,
    RetryableError,
)
from apps.modulos.common.pagination import (
    get_limit_offset,
    paginate_list,
    paginate_queryset,
)
from apps.modulos.common.permissions import rbac_permission
from apps.modulos.common.throttling import MethodThrottleScopeMixin
from apps.modulos.iam.models import OrgUnit, UserMembership

User = get_user_model()


# ---------------------------------------------------------------------------
# domain_errors
# ---------------------------------------------------------------------------

def test_domain_error_defaults():
    e = DomainError("boom")
    assert e.message == "boom"
    assert e.code == "DOMAIN_ERROR"
    assert e.retryable is False
    assert e.context == {}
    assert e.as_payload() == {
        "message": "boom",
        "code": "DOMAIN_ERROR",
        "retryable": False,
        "context": {},
    }
    assert isinstance(e, Exception)


def test_domain_error_custom_fields():
    e = DomainError("x", code="E1", context={"a": 1}, retryable=True)
    assert e.code == "E1"
    assert e.retryable is True
    assert e.context == {"a": 1}
    # as_payload copia el contexto (no comparte la referencia mutable)
    payload = e.as_payload()
    payload["context"]["a"] = 999
    assert e.context == {"a": 1}


def test_integration_and_retryable_hierarchy():
    assert IntegrationError("x").code == "INTEGRATION_ERROR"
    assert IntegrationError("x").retryable is False
    r = RetryableError("x")
    assert r.code == "RETRYABLE_ERROR"
    assert r.retryable is True
    assert isinstance(r, IntegrationError)
    assert isinstance(r, DomainError)


# ---------------------------------------------------------------------------
# api_exceptions
# ---------------------------------------------------------------------------

def test_conflict_error_status_and_code():
    err = ConflictError()
    assert err.status_code == 409
    assert ConflictError.default_code == "CONFLICT"
    custom = ConflictError("Ya existe")
    assert str(custom.detail) == "Ya existe"


# ---------------------------------------------------------------------------
# pagination
# ---------------------------------------------------------------------------

def _req(params: dict) -> SimpleNamespace:
    return SimpleNamespace(query_params=params)


def test_get_limit_offset_defaults():
    assert get_limit_offset(_req({})) == (50, 0)


def test_get_limit_offset_clamps_max_and_negative_offset():
    assert get_limit_offset(_req({"limit": "9999", "offset": "-5"})) == (200, 0)


def test_get_limit_offset_min_one():
    assert get_limit_offset(_req({"limit": "0"}))[0] == 1


def test_get_limit_offset_garbage_falls_back_to_defaults():
    assert get_limit_offset(_req({"limit": "abc", "offset": "xyz"})) == (50, 0)


def test_get_limit_offset_respects_custom_bounds():
    assert get_limit_offset(_req({"limit": "100"}), default_limit=10, max_limit=20) == (20, 0)


def test_paginate_list_slices():
    total, page = paginate_list(list(range(10)), limit=3, offset=2)
    assert total == 10
    assert page == [2, 3, 4]


@pytest.mark.django_db
def test_paginate_queryset_counts_and_slices():
    for i in range(5):
        OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"pg_{i}_{uuid.uuid4().hex[:4]}")
    qs = OrgUnit.objects.all().order_by("id")
    total, rows = paginate_queryset(qs, limit=2, offset=1)
    assert total == 5
    assert len(list(rows)) == 2


# ---------------------------------------------------------------------------
# tender
# ---------------------------------------------------------------------------

def test_tender_catalog_and_sets():
    assert t.UNKNOWN_TENDER_PAYMENT_METHOD == ""
    # El catálogo de choices antepone la opción "sin especificar".
    assert t.TENDER_PAYMENT_METHOD_CHOICES[0] == ("", "Sin especificar")
    assert ("CASH", "Efectivo") in t.TenderPaymentMethod.choices
    # El frozenset de valores excluye el desconocido "" e incluye los reales.
    assert "" not in t.TENDER_PAYMENT_METHOD_VALUES
    assert {"CASH", "MIXED", "TRANSFER"} <= t.TENDER_PAYMENT_METHOD_VALUES
    # CASH y MIXED no son "no-efectivo"; TRANSFER sí.
    assert t.TenderPaymentMethod.CASH not in t.NON_CASH_TENDER_PAYMENT_METHODS
    assert t.TenderPaymentMethod.MIXED not in t.NON_CASH_TENDER_PAYMENT_METHODS
    assert t.TenderPaymentMethod.TRANSFER in t.NON_CASH_TENDER_PAYMENT_METHODS
    # Todo "no-efectivo" es un valor válido del catálogo.
    assert {m.value for m in t.NON_CASH_TENDER_PAYMENT_METHODS} <= t.TENDER_PAYMENT_METHOD_VALUES


# ---------------------------------------------------------------------------
# throttling: MethodThrottleScopeMixin
# ---------------------------------------------------------------------------

class _ThrottleBase:
    def get_throttles(self):
        self.super_called = True
        return ["sentinel"]


def _throttle_view(mapping, *, default=None, method="GET"):
    class _V(MethodThrottleScopeMixin, _ThrottleBase):
        throttle_scope_by_method = mapping
        default_throttle_scope = default

    v = _V()
    v.request = SimpleNamespace(method=method)
    out = v.get_throttles()
    return v, out


def test_throttle_scope_by_method_selected():
    v, out = _throttle_view({"GET": "heavy_reads", "POST": "admin_writes"}, method="GET")
    assert v.throttle_scope == "heavy_reads"
    assert v.super_called is True
    assert out == ["sentinel"]


def test_throttle_scope_falls_back_to_default():
    v, _ = _throttle_view({"GET": "heavy_reads"}, default="fallback", method="DELETE")
    assert v.throttle_scope == "fallback"


def test_throttle_scope_unset_when_no_mapping_no_default():
    v, _ = _throttle_view({}, method="GET")
    assert getattr(v, "throttle_scope", None) is None


# ---------------------------------------------------------------------------
# permissions: rbac_permission (factory DRF)
# ---------------------------------------------------------------------------

def _perm(code="inventory.read"):
    return rbac_permission(code)()


def test_rbac_denies_anonymous_and_marks_required_permission():
    perm = _perm()
    req = SimpleNamespace(user=SimpleNamespace(is_authenticated=False))
    assert perm.has_permission(req, None) is False
    assert req.required_permission == "inventory.read"


def test_rbac_denies_when_no_company_context():
    perm = _perm()
    req = SimpleNamespace(
        user=SimpleNamespace(is_authenticated=True),
        company=None,
        branch=None,
    )
    assert perm.has_permission(req, None) is False
    assert req.required_scope == {"company_id": None, "branch_id": None}


def test_rbac_allows_with_override_permission():
    perm = _perm()
    req = SimpleNamespace(
        user=SimpleNamespace(is_authenticated=True),
        company=SimpleNamespace(id=1),
        branch=None,
        rbac_effective_permissions_override={"inventory.read"},
    )
    assert perm.has_permission(req, None) is True


def test_rbac_allows_with_wildcard_override():
    perm = _perm()
    req = SimpleNamespace(
        user=SimpleNamespace(is_authenticated=True),
        company=SimpleNamespace(id=1),
        branch=None,
        rbac_effective_permissions_override={"*"},
    )
    assert perm.has_permission(req, None) is True


def test_rbac_denies_without_required_permission_and_sets_scope():
    perm = _perm()
    req = SimpleNamespace(
        user=SimpleNamespace(is_authenticated=True),
        company=SimpleNamespace(id=5),
        branch=SimpleNamespace(id=7),
        rbac_effective_permissions_override=set(),
    )
    assert perm.has_permission(req, None) is False
    assert req.required_scope == {"company_id": 5, "branch_id": 7}


def test_rbac_intercompany_denied(monkeypatch):
    import apps.modulos.iam.selectors as iam_sel

    monkeypatch.setattr(iam_sel, "has_intercompany_grant", lambda **kw: False)
    perm = _perm()
    req = SimpleNamespace(
        user=SimpleNamespace(is_authenticated=True),
        company=SimpleNamespace(id=1),
        branch=None,
        rbac_effective_permissions_override={"inventory.read"},
        data_company=SimpleNamespace(id=2),
        data_branch=None,
    )
    assert perm.has_permission(req, None) is False
    assert req.required_scope == {"company_id": 2, "branch_id": None}
    assert req.intercompany["grant_found"] is False


def test_rbac_intercompany_allowed(monkeypatch):
    import apps.modulos.iam.selectors as iam_sel

    monkeypatch.setattr(iam_sel, "has_intercompany_grant", lambda **kw: True)
    perm = _perm()
    req = SimpleNamespace(
        user=SimpleNamespace(is_authenticated=True),
        company=SimpleNamespace(id=1),
        branch=None,
        rbac_effective_permissions_override={"inventory.read"},
        data_company=SimpleNamespace(id=2),
        data_branch=None,
    )
    assert perm.has_permission(req, None) is True
    assert req.intercompany["grant_found"] is True


# ---------------------------------------------------------------------------
# MetricsView (API) — /api/metrics/
# ---------------------------------------------------------------------------

def _mk_user(*, staff=False, superuser=False):
    username = f"m_{uuid.uuid4().hex[:8]}"
    if superuser:
        return User.objects.create_superuser(
            username=username, email=f"{username}@test.local", password="pass12345"
        )
    return User.objects.create_user(
        username=username,
        email=f"{username}@test.local",
        password="pass12345",
        is_staff=staff,
    )


def _mk_org():
    s = uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H_{s}")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name=f"C_{s}", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name=f"B_{s}", parent=company)
    return company, branch


def _login(user, *, company=None, branch=None) -> APIClient:
    client = APIClient()
    login = client.post(
        "/api/auth/login/",
        {"username": user.username, "password": "pass12345"},
        format="json",
    )
    assert login.status_code == 200, login.data
    access = login.data.get("access") if isinstance(login.data, dict) else None
    assert access
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    # El middleware de contexto exige empresa activa para endpoints autenticados.
    if company is not None:
        client.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    if branch is not None:
        client.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    return client


def _login_with_context(user) -> APIClient:
    company, branch = _mk_org()
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)
    return _login(user, company=company, branch=branch)


@pytest.mark.django_db
def test_metrics_requires_authentication():
    resp = APIClient().get("/api/metrics/")
    assert resp.status_code in (401, 403)


@pytest.mark.django_db
def test_metrics_forbidden_for_non_staff():
    client = _login_with_context(_mk_user())
    resp = client.get("/api/metrics/")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_metrics_ok_for_superuser(monkeypatch):
    import apps.modulos.common.views as cv

    monkeypatch.setattr(cv, "snapshot", lambda: {"base": 1})
    monkeypatch.setattr(cv, "build_reporting_observability", lambda **k: {"r": 1})
    monkeypatch.setattr(cv, "build_dashboard_observability", lambda **k: {"d": 1})

    client = _login_with_context(_mk_user(superuser=True))
    resp = client.get("/api/metrics/")
    assert resp.status_code == 200
    assert resp.data == {"base": 1, "reporting": {"r": 1}, "dashboard": {"d": 1}}
