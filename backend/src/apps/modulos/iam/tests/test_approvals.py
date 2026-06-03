"""Tests de la primitiva SoD / maker-checker (iam.approvals)."""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model

from apps.modulos.iam.approvals import (
    ApprovalStateError,
    ApproverNotAuthorizedError,
    SelfApprovalError,
    approve,
    cancel,
    mark_executed,
    reject,
    request_approval,
)
from apps.modulos.iam.models import ApprovalRequest, OrgUnit
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()

PERM = "billing.doc.void"


def _mk_org():
    s = uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H_{s}")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name=f"C_{s}", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name=f"B_{s}", parent=company)
    return company, branch


def _mk_user(prefix="ap"):
    username = f"{prefix}_{uuid.uuid4().hex[:8]}"
    return User.objects.create_user(username=username, email=f"{username}@test.local", password="pass12345")


def _grant(user, company, perm_code=PERM):
    role = Role.objects.create(name=f"role_{uuid.uuid4().hex[:8]}", is_active=True)
    perm, _ = Permission.objects.get_or_create(code=perm_code, defaults={"description": perm_code, "is_active": True})
    RolePermission.objects.create(role=role, permission=perm)
    RoleAssignment.objects.create(user=user, role=role, org_unit=company, is_active=True)


def _request(company, branch, maker, **over):
    params = dict(
        company=company,
        branch=branch,
        requested_by=maker,
        action_type="BILLING_DOC_VOID",
        required_permission=PERM,
        subject_type="BILLING_DOC",
        subject_id="123",
        reason="anular doc",
    )
    params.update(over)
    return request_approval(**params)


@pytest.mark.django_db
def test_request_creates_pending_and_is_idempotent():
    company, branch = _mk_org()
    maker = _mk_user()
    a1 = _request(company, branch, maker, idempotency_key="k1")
    assert a1.status == ApprovalRequest.Status.PENDING
    a2 = _request(company, branch, maker, idempotency_key="k1")
    assert a2.id == a1.id  # idempotente
    assert ApprovalRequest.objects.filter(company=company).count() == 1


@pytest.mark.django_db
def test_approve_by_authorized_checker():
    company, branch = _mk_org()
    maker = _mk_user("maker")
    checker = _mk_user("checker")
    _grant(checker, company)
    approval = _request(company, branch, maker)

    out = approve(approval=approval, approver=checker, note="ok")
    assert out.status == ApprovalRequest.Status.APPROVED
    assert out.decided_by_id == checker.id
    assert out.decided_at is not None


@pytest.mark.django_db
def test_self_approval_is_blocked_sod():
    company, branch = _mk_org()
    maker = _mk_user("maker")
    _grant(maker, company)  # aunque tenga el permiso, no puede auto-aprobar
    approval = _request(company, branch, maker)
    with pytest.raises(SelfApprovalError):
        approve(approval=approval, approver=maker)


@pytest.mark.django_db
def test_approver_without_permission_is_rejected():
    company, branch = _mk_org()
    maker = _mk_user("maker")
    checker = _mk_user("checker")  # sin permiso
    approval = _request(company, branch, maker)
    with pytest.raises(ApproverNotAuthorizedError):
        approve(approval=approval, approver=checker)


@pytest.mark.django_db
def test_superuser_can_approve_without_explicit_permission():
    company, branch = _mk_org()
    maker = _mk_user("maker")
    su = User.objects.create_superuser(
        username=f"su_{uuid.uuid4().hex[:6]}", email="su@test.local", password="pass12345"
    )
    approval = _request(company, branch, maker)
    out = approve(approval=approval, approver=su)
    assert out.status == ApprovalRequest.Status.APPROVED


@pytest.mark.django_db
def test_reject_and_cancel_flows():
    company, branch = _mk_org()
    maker = _mk_user("maker")
    checker = _mk_user("checker")
    _grant(checker, company)

    a1 = _request(company, branch, maker)
    rejected = reject(approval=a1, approver=checker, note="no")
    assert rejected.status == ApprovalRequest.Status.REJECTED

    a2 = _request(company, branch, maker)
    cancelled = cancel(approval=a2, actor=maker)
    assert cancelled.status == ApprovalRequest.Status.CANCELLED


@pytest.mark.django_db
def test_cancel_by_non_maker_is_blocked():
    company, branch = _mk_org()
    maker = _mk_user("maker")
    other = _mk_user("other")
    approval = _request(company, branch, maker)
    with pytest.raises(ApproverNotAuthorizedError):
        cancel(approval=approval, actor=other)


@pytest.mark.django_db
def test_decide_on_non_pending_raises_state_error():
    company, branch = _mk_org()
    maker = _mk_user("maker")
    checker = _mk_user("checker")
    _grant(checker, company)
    approval = _request(company, branch, maker)
    approve(approval=approval, approver=checker)
    with pytest.raises(ApprovalStateError):
        reject(approval=approval, approver=checker)


@pytest.mark.django_db
def test_mark_executed_requires_approved():
    company, branch = _mk_org()
    maker = _mk_user("maker")
    checker = _mk_user("checker")
    _grant(checker, company)
    approval = _request(company, branch, maker)

    with pytest.raises(ApprovalStateError):
        mark_executed(approval=approval)  # aún PENDING

    approve(approval=approval, approver=checker)
    done = mark_executed(approval=approval, actor=checker)
    assert done.status == ApprovalRequest.Status.EXECUTED
