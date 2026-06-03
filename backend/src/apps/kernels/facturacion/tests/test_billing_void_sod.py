"""Tests de SoD (maker-checker) en anulación de documentos de facturación.

Integra la primitiva iam.approvals con el flujo real create_draft -> issue_doc ->
(request_void -> approve_and_void) del kernel de facturación.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model

from apps.kernels.facturacion.models import BillingDocument, DocStatus
from apps.kernels.facturacion.services import create_draft, issue_doc
from apps.kernels.facturacion.void_sod import (
    VOID_APPROVE_PERMISSION,
    approve_and_void,
    request_void,
)
from apps.modulos.iam.approvals import ApproverNotAuthorizedError, SelfApprovalError
from apps.modulos.iam.models import ApprovalRequest, OrgUnit
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()


def _scope():
    t = uuid.uuid4().hex[:8]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H{t}", code=f"H-{t}")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, parent=holding, name=f"C{t}", code=f"C-{t}")
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, parent=company, name=f"B{t}", code=f"B-{t}")
    return company, branch


def _user(prefix="u"):
    t = uuid.uuid4().hex[:8]
    return User.objects.create_user(username=f"{prefix}_{t}", email=f"{prefix}_{t}@test.local", password="Secret123!")


def _request(company, branch, user):
    return SimpleNamespace(
        company=company, branch=branch, user=user, META={}, headers={},
        path="/test/billing/", method="POST", request_id=f"req-{uuid.uuid4().hex[:8]}",
    )


def _grant(user, company, perm_code):
    role = Role.objects.create(name=f"role_{uuid.uuid4().hex[:8]}", is_active=True)
    perm, _ = Permission.objects.get_or_create(code=perm_code, defaults={"description": perm_code, "is_active": True})
    RolePermission.objects.create(role=role, permission=perm)
    RoleAssignment.objects.create(user=user, role=role, org_unit=company, is_active=True)


def _issued_doc(request, actor) -> int:
    draft = create_draft(
        request=request,
        actor=actor,
        doc_type="INVOICE",
        series="A",
        currency="NIO",
        customer_name="Cliente Demo",
        customer_ref="C-001",
        is_fiscal=False,
        lines=[{"description": "Servicio", "quantity": "1", "unit_price": "100", "tax_rate": "0.15"}],
        idempotency_key=f"draft-{uuid.uuid4().hex}",
    )
    issue_doc(
        request=request,
        actor=actor,
        doc_id=draft.doc_id,
        apply_inventory=False,
        print_after_issue=False,
        idempotency_key=f"issue-{uuid.uuid4().hex}",
    )
    return draft.doc_id


@pytest.mark.django_db
def test_void_requires_second_approver_and_voids_on_approval():
    company, branch = _scope()
    maker = _user("maker")
    checker = _user("checker")
    _grant(checker, company, VOID_APPROVE_PERMISSION)

    maker_req = _request(company, branch, maker)
    doc_id = _issued_doc(maker_req, maker)

    approval = request_void(request=maker_req, actor=maker, doc_id=doc_id, reason="error de captura")
    assert approval.status == ApprovalRequest.Status.PENDING
    # El documento sigue emitido hasta la aprobación.
    assert BillingDocument.objects.get(id=doc_id).status == DocStatus.ISSUED

    checker_req = _request(company, branch, checker)
    result = approve_and_void(request=checker_req, approver=checker, approval=approval)
    assert result.get("ok") is not False
    assert BillingDocument.objects.get(id=doc_id).status == DocStatus.VOIDED
    approval.refresh_from_db()
    assert approval.status == ApprovalRequest.Status.EXECUTED


@pytest.mark.django_db
def test_maker_cannot_self_approve_void():
    company, branch = _scope()
    maker = _user("maker")
    _grant(maker, company, VOID_APPROVE_PERMISSION)  # aún con permiso, no puede auto-aprobar

    maker_req = _request(company, branch, maker)
    doc_id = _issued_doc(maker_req, maker)
    approval = request_void(request=maker_req, actor=maker, doc_id=doc_id, reason="x")
    with pytest.raises(SelfApprovalError):
        approve_and_void(request=maker_req, approver=maker, approval=approval)
    assert BillingDocument.objects.get(id=doc_id).status == DocStatus.ISSUED


@pytest.mark.django_db
def test_approver_without_permission_cannot_void():
    company, branch = _scope()
    maker = _user("maker")
    checker = _user("checker")  # sin permiso de aprobación

    maker_req = _request(company, branch, maker)
    doc_id = _issued_doc(maker_req, maker)
    approval = request_void(request=maker_req, actor=maker, doc_id=doc_id, reason="x")
    checker_req = _request(company, branch, checker)
    with pytest.raises(ApproverNotAuthorizedError):
        approve_and_void(request=checker_req, approver=checker, approval=approval)
    assert BillingDocument.objects.get(id=doc_id).status == DocStatus.ISSUED
