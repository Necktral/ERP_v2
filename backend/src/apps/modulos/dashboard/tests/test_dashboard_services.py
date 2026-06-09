"""
Tests del módulo dashboard — workspaces y tokens embed (JTI), single-use y scope.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model

from apps.modulos.dashboard.models import DashboardEmbedGrant
from apps.modulos.dashboard.services import (
    DashboardAuthError,
    DashboardConflictError,
    DashboardPermissionDenied,
    DashboardValidationError,
    create_embed_token_for_request,
    list_workspaces_for_request,
    redeem_embed_token,
)
from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()

# Permisos requeridos por el workspace "executive".
_EXEC_PERMS = ("report.dashboard.read", "report.dataset.read", "accounting.report.read")


def _mk_scope(suffix=""):
    s = suffix or uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H_{s}")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name=f"C_{s}", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name=f"B_{s}", parent=company)
    return company, branch


def _user_with_perms(*, company, branch, perms):
    u = User.objects.create_user(username=f"u_{uuid.uuid4().hex[:8]}", password="x")
    UserMembership.objects.create(user=u, org_unit=company, is_active=True)
    UserMembership.objects.create(user=u, org_unit=branch, is_active=True)
    role = Role.objects.create(name=f"r_{uuid.uuid4().hex[:8]}", is_active=True)
    for p in perms:
        perm, _ = Permission.objects.get_or_create(code=p, defaults={"description": p, "is_active": True})
        RolePermission.objects.get_or_create(role=role, permission=perm)
    RoleAssignment.objects.create(user=u, role=role, org_unit=company, is_active=True)
    RoleAssignment.objects.create(user=u, role=role, org_unit=branch, is_active=True)
    return u


def _request(user, company, branch):
    # write_event lee META/path/method (un DRF request real los trae).
    return SimpleNamespace(
        user=user, company=company, branch=branch, META={}, path="", method="POST",
    )


# ---------------------------------------------------------------------------
# list_workspaces_for_request
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_list_workspaces_visible_with_perms():
    company, branch = _mk_scope()
    user = _user_with_perms(company=company, branch=branch, perms=_EXEC_PERMS)
    rows = list_workspaces_for_request(request=_request(user, company, branch))
    keys = {r["workspace_key"] for r in rows}
    assert "executive" in keys


@pytest.mark.django_db
def test_list_workspaces_hidden_without_perms():
    company, branch = _mk_scope()
    user = _user_with_perms(company=company, branch=branch, perms=["unrelated.perm"])
    rows = list_workspaces_for_request(request=_request(user, company, branch))
    assert rows == []


@pytest.mark.django_db
def test_list_workspaces_unauthenticated_raises():
    company, branch = _mk_scope()
    anon = SimpleNamespace(user=SimpleNamespace(is_authenticated=False), company=company, branch=branch)
    with pytest.raises(DashboardAuthError):
        list_workspaces_for_request(request=anon)


@pytest.mark.django_db
def test_list_workspaces_no_company_raises():
    company, branch = _mk_scope()
    user = _user_with_perms(company=company, branch=branch, perms=_EXEC_PERMS)
    with pytest.raises(DashboardValidationError):
        list_workspaces_for_request(request=SimpleNamespace(user=user, company=None, branch=branch))


# ---------------------------------------------------------------------------
# create_embed_token_for_request
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_create_embed_token_success():
    company, branch = _mk_scope()
    user = _user_with_perms(company=company, branch=branch, perms=_EXEC_PERMS)
    out = create_embed_token_for_request(
        request=_request(user, company, branch), workspace_key="executive",
    )
    assert out["workspace_key"] == "executive"
    assert "bootstrap_url" in out
    grant = DashboardEmbedGrant.objects.get(id=out["embed_grant_id"])
    assert grant.status == DashboardEmbedGrant.Status.ISSUED
    assert grant.company == company


@pytest.mark.django_db
def test_create_embed_token_missing_perms_denied():
    company, branch = _mk_scope()
    user = _user_with_perms(company=company, branch=branch, perms=["report.dashboard.read"])  # incompleto
    with pytest.raises(DashboardPermissionDenied):
        create_embed_token_for_request(
            request=_request(user, company, branch), workspace_key="executive",
        )


@pytest.mark.django_db
def test_create_embed_token_invalid_workspace_raises():
    company, branch = _mk_scope()
    user = _user_with_perms(company=company, branch=branch, perms=_EXEC_PERMS)
    with pytest.raises(DashboardValidationError):
        create_embed_token_for_request(
            request=_request(user, company, branch), workspace_key="nope",
        )


# ---------------------------------------------------------------------------
# redeem_embed_token — single use + scope
# ---------------------------------------------------------------------------

def _issue_token(user, company, branch):
    """Re-emite el JWT crudo (no expuesto por create) para poder canjearlo."""
    from datetime import timedelta
    from rest_framework_simplejwt.tokens import AccessToken
    # Reproduce el grant vía servicio y construye el token equivalente.
    out = create_embed_token_for_request(
        request=_request(user, company, branch), workspace_key="executive",
    )
    grant = DashboardEmbedGrant.objects.get(id=out["embed_grant_id"])
    token = AccessToken.for_user(user)
    token["purpose"] = "dash_embed"
    token["company_id"] = int(company.id)
    token["branch_id"] = int(branch.id)
    token["workspace_key"] = "executive"
    token["jti"] = grant.jti  # alinear con el grant persistido
    token.set_exp(lifetime=timedelta(seconds=90))
    return str(token), grant


@pytest.mark.django_db
def test_redeem_token_success_then_conflict_on_reuse():
    company, branch = _mk_scope()
    user = _user_with_perms(company=company, branch=branch, perms=_EXEC_PERMS)
    raw, grant = _issue_token(user, company, branch)

    result = redeem_embed_token(token_str=raw)
    assert result is not None
    grant.refresh_from_db()
    assert grant.status == DashboardEmbedGrant.Status.REDEEMED

    # Segundo canje del mismo token → conflicto (single-use)
    with pytest.raises(DashboardConflictError):
        redeem_embed_token(token_str=raw)


@pytest.mark.django_db
def test_redeem_empty_token_raises():
    with pytest.raises(DashboardValidationError):
        redeem_embed_token(token_str="")


@pytest.mark.django_db
def test_redeem_garbage_token_raises_auth():
    with pytest.raises(DashboardAuthError):
        redeem_embed_token(token_str="not-a-real-jwt")


# ---------------------------------------------------------------------------
# Auditoría (quién/qué/cuándo/en qué) — mint + redeem de embed token
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_embed_token_mint_and_redeem_emit_audit():
    from apps.modulos.audit.models import AuditEvent

    company, branch = _mk_scope()
    user = _user_with_perms(company=company, branch=branch, perms=_EXEC_PERMS)
    raw, grant = _issue_token(user, company, branch)
    redeem_embed_token(token_str=raw)

    minted = AuditEvent.objects.filter(
        event_type="DASHBOARD_EMBED_TOKEN_MINTED", subject_type="DASHBOARD_EMBED", subject_id=str(grant.id)
    ).first()
    assert minted is not None and minted.actor_user_id == user.id and minted.module == "DASHBOARD"

    redeemed = AuditEvent.objects.filter(
        event_type="DASHBOARD_EMBED_TOKEN_REDEEMED", subject_type="DASHBOARD_EMBED", subject_id=str(grant.id)
    ).first()
    assert redeemed is not None and redeemed.actor_user_id == user.id
    assert redeemed.after_snapshot.get("status") == DashboardEmbedGrant.Status.REDEEMED
