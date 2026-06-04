"""Tests de SoD (maker-checker) en payments (Unidad #3, incremento #3).

Dos operaciones sensibles bajo doble control (invariante #6), reusando
`apps.modulos.iam.approvals`:
- Reembolso de PaymentIntent (`payments.refund.approve`).
- Reapertura de CashSession para investigación (`payments.cash.reopen.approve`).

Cubre nivel servicio (maker/checker, self-approval, sin permiso) y nivel API
(hard-gate: el endpoint directo ya no reembolsa/reabre, sino que crea la
solicitud; el checker ejecuta).
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.kernels.payments.models import CashSession, PaymentIntent
from apps.kernels.payments.services import (
    capture_payment_intent_for_scope,
    close_cash_session_for_scope,
    create_payment_intent_for_scope,
    open_cash_session_for_scope,
)
from apps.kernels.payments.sod import (
    CASH_REOPEN_APPROVE_PERMISSION,
    REFUND_APPROVE_PERMISSION,
    approve_and_refund,
    approve_and_reopen,
    request_refund,
    request_reopen,
)
from apps.modulos.iam.approvals import ApproverNotAuthorizedError, SelfApprovalError
from apps.modulos.iam.models import ApprovalRequest, OrgUnit, UserMembership
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()


def _scope():
    s = uuid.uuid4().hex[:8]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H{s}")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name=f"C{s}", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name=f"B{s}", parent=company)
    return company, branch


def _user(prefix="u"):
    t = uuid.uuid4().hex[:8]
    return User.objects.create_user(username=f"{prefix}_{t}", email=f"{prefix}_{t}@test.local", password="Secret123!")


def _request(company, branch, user):
    return SimpleNamespace(
        company=company, branch=branch, user=user, META={}, headers={},
        path="/test/payments/", method="POST", request_id=f"req-{uuid.uuid4().hex[:8]}",
    )


def _grant(user, company, *perm_codes):
    role = Role.objects.create(name=f"role_{uuid.uuid4().hex[:8]}", is_active=True)
    for perm_code in perm_codes:
        perm, _ = Permission.objects.get_or_create(
            code=perm_code, defaults={"description": perm_code, "is_active": True}
        )
        RolePermission.objects.create(role=role, permission=perm)
    RoleAssignment.objects.create(user=user, role=role, org_unit=company, is_active=True)


def _captured_intent(*, company, branch, actor, amount="200.00"):
    intent, _ = create_payment_intent_for_scope(
        company=company, branch=branch, actor=actor,
        amount=Decimal(amount), currency="NIO", payment_method="CARD",
        idempotency_key=f"k-{uuid.uuid4().hex}",
    )
    captured = capture_payment_intent_for_scope(
        company=company, branch=branch, actor=actor, payment_id=intent.payment_id
    )
    captured.amount_captured = Decimal(amount)
    captured.save(update_fields=["amount_captured"])
    return captured


def _closed_session(*, company, branch, actor, register_id="RS"):
    s = open_cash_session_for_scope(
        company=company, branch=branch, actor=actor, opening_amount=Decimal("100.00"), register_id=register_id
    )
    close_cash_session_for_scope(
        company=company, branch=branch, actor=actor, session_id=s.id, counted_amount=Decimal("100.00")
    )
    return s


def _api_client(*, company, branch, perms):
    u = _user("api")
    UserMembership.objects.create(user=u, org_unit=company, is_active=True)
    UserMembership.objects.create(user=u, org_unit=branch, is_active=True)
    _grant(u, company, *perms)
    # branch-scope para permisos efectivos por sucursal
    role = Role.objects.create(name=f"role_b_{uuid.uuid4().hex[:8]}", is_active=True)
    for p in perms:
        perm, _ = Permission.objects.get_or_create(code=p, defaults={"description": p, "is_active": True})
        RolePermission.objects.get_or_create(role=role, permission=perm)
    RoleAssignment.objects.create(user=u, role=role, org_unit=branch, is_active=True)
    c = APIClient()
    login = c.post("/api/auth/login/", {"username": u.username, "password": "Secret123!"}, format="json")
    assert login.status_code == 200, login.data
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    c.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    c.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    return c, u


# --------------------------------------------------------------------------- #
# Refund — nivel servicio
# --------------------------------------------------------------------------- #

@pytest.mark.django_db
def test_refund_requires_second_approver():
    company, branch = _scope()
    maker, checker = _user("maker"), _user("checker")
    _grant(checker, company, REFUND_APPROVE_PERMISSION)
    intent = _captured_intent(company=company, branch=branch, actor=maker)

    approval = request_refund(
        request=_request(company, branch, maker), actor=maker,
        payment_id=intent.payment_id, amount=Decimal("50.00"), reason="ajuste",
    )
    assert approval.status == ApprovalRequest.Status.PENDING
    intent.refresh_from_db()
    assert intent.amount_refunded == Decimal("0.00")  # aún no reembolsado

    refund = approve_and_refund(
        request=_request(company, branch, checker), approver=checker, approval=approval
    )
    assert refund.amount == Decimal("50.00")
    intent.refresh_from_db()
    assert intent.amount_refunded == Decimal("50.00")
    assert intent.status == PaymentIntent.Status.PARTIALLY_REFUNDED
    approval.refresh_from_db()
    assert approval.status == ApprovalRequest.Status.EXECUTED


@pytest.mark.django_db
def test_maker_cannot_self_approve_refund():
    company, branch = _scope()
    maker = _user("maker")
    _grant(maker, company, REFUND_APPROVE_PERMISSION)  # aún con permiso, no puede auto-aprobar
    intent = _captured_intent(company=company, branch=branch, actor=maker)
    approval = request_refund(
        request=_request(company, branch, maker), actor=maker,
        payment_id=intent.payment_id, amount=Decimal("50.00"),
    )
    with pytest.raises(SelfApprovalError):
        approve_and_refund(request=_request(company, branch, maker), approver=maker, approval=approval)
    intent.refresh_from_db()
    assert intent.amount_refunded == Decimal("0.00")


@pytest.mark.django_db
def test_approver_without_permission_cannot_refund():
    company, branch = _scope()
    maker, checker = _user("maker"), _user("checker")  # checker sin permiso
    intent = _captured_intent(company=company, branch=branch, actor=maker)
    approval = request_refund(
        request=_request(company, branch, maker), actor=maker,
        payment_id=intent.payment_id, amount=Decimal("50.00"),
    )
    with pytest.raises(ApproverNotAuthorizedError):
        approve_and_refund(request=_request(company, branch, checker), approver=checker, approval=approval)
    intent.refresh_from_db()
    assert intent.amount_refunded == Decimal("0.00")


# --------------------------------------------------------------------------- #
# Reopen — nivel servicio
# --------------------------------------------------------------------------- #

@pytest.mark.django_db
def test_reopen_requires_second_approver():
    company, branch = _scope()
    maker, checker = _user("maker"), _user("checker")
    _grant(checker, company, CASH_REOPEN_APPROVE_PERMISSION)
    s = _closed_session(company=company, branch=branch, actor=maker)

    approval = request_reopen(
        request=_request(company, branch, maker), actor=maker, session_id=s.id, reason="auditoría"
    )
    assert approval.status == ApprovalRequest.Status.PENDING
    s.refresh_from_db()
    assert s.status == CashSession.Status.CLOSED  # aún cerrada

    session = approve_and_reopen(
        request=_request(company, branch, checker), approver=checker, approval=approval
    )
    assert session.status == CashSession.Status.REOPENED_FOR_INVESTIGATION
    approval.refresh_from_db()
    assert approval.status == ApprovalRequest.Status.EXECUTED


@pytest.mark.django_db
def test_maker_cannot_self_approve_reopen():
    company, branch = _scope()
    maker = _user("maker")
    _grant(maker, company, CASH_REOPEN_APPROVE_PERMISSION)
    s = _closed_session(company=company, branch=branch, actor=maker)
    approval = request_reopen(
        request=_request(company, branch, maker), actor=maker, session_id=s.id, reason="x"
    )
    with pytest.raises(SelfApprovalError):
        approve_and_reopen(request=_request(company, branch, maker), approver=maker, approval=approval)
    s.refresh_from_db()
    assert s.status == CashSession.Status.CLOSED


@pytest.mark.django_db
def test_approver_without_permission_cannot_reopen():
    company, branch = _scope()
    maker, checker = _user("maker"), _user("checker")
    s = _closed_session(company=company, branch=branch, actor=maker)
    approval = request_reopen(
        request=_request(company, branch, maker), actor=maker, session_id=s.id, reason="x"
    )
    with pytest.raises(ApproverNotAuthorizedError):
        approve_and_reopen(request=_request(company, branch, checker), approver=checker, approval=approval)
    s.refresh_from_db()
    assert s.status == CashSession.Status.CLOSED


# --------------------------------------------------------------------------- #
# Refund — nivel API (hard-gate + flujo maker-checker)
# --------------------------------------------------------------------------- #

@pytest.mark.django_db
def test_refund_endpoint_is_hard_gated_and_flows_via_approval():
    company, branch = _scope()
    maker_c, maker = _api_client(company=company, branch=branch, perms=["payments.refund.request"])
    checker_c, _checker = _api_client(company=company, branch=branch, perms=["payments.refund.approve"])
    intent = _captured_intent(company=company, branch=branch, actor=maker)

    # maker POST /refund/ -> 202 (crea solicitud, NO reembolsa directo)
    r = maker_c.post(
        f"/api/payments/intents/{intent.payment_id}/refund/",
        {"amount": "50.00", "reason": "x"}, format="json",
    )
    assert r.status_code == 202, r.data
    rid = r.data["approval_request_id"]
    intent.refresh_from_db()
    assert intent.amount_refunded == Decimal("0.00")

    # checker aprueba -> 201 (ejecuta el reembolso)
    r2 = checker_c.post(f"/api/payments/approvals/{rid}/refund/approve/", {}, format="json")
    assert r2.status_code == 201, r2.data
    intent.refresh_from_db()
    assert intent.amount_refunded == Decimal("50.00")


@pytest.mark.django_db
def test_refund_self_approval_forbidden_via_api():
    company, branch = _scope()
    # mismo usuario con ambos permisos: igual no puede auto-aprobar (SoD -> 403)
    maker_c, maker = _api_client(
        company=company, branch=branch, perms=["payments.refund.request", "payments.refund.approve"]
    )
    intent = _captured_intent(company=company, branch=branch, actor=maker)
    r = maker_c.post(
        f"/api/payments/intents/{intent.payment_id}/refund/",
        {"amount": "50.00"}, format="json",
    )
    assert r.status_code == 202, r.data
    rid = r.data["approval_request_id"]
    r2 = maker_c.post(f"/api/payments/approvals/{rid}/refund/approve/", {}, format="json")
    assert r2.status_code == 403, r2.data
    intent.refresh_from_db()
    assert intent.amount_refunded == Decimal("0.00")
