from __future__ import annotations

from datetime import timedelta
import uuid

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.kernels.facturacion.models import BillingDocument
from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.rbac.models import Role, Permission, RoleAssignment, RolePermission
from apps.modulos.accounts.models import User
from apps.modulos.audit.models import AuditEvent


def _mk_scope():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B", parent=company)
    return company, branch


def _client_with_perms(user: User, company: OrgUnit, branch: OrgUnit, perms: list[str]) -> APIClient:
    role = Role.objects.create(name=f"tmp_role2_{uuid.uuid4().hex[:8]}", is_active=True)
    for p in perms:
        perm, _ = Permission.objects.get_or_create(code=p, defaults={"description": p, "is_active": True})
        RolePermission.objects.get_or_create(role=role, permission=perm)

    # RBAC scoped real: RoleAssignment se asigna por org_unit (COMPANY y/o BRANCH)
    RoleAssignment.objects.create(user=user, role=role, org_unit=company, origin=RoleAssignment.Origin.MANUAL)
    RoleAssignment.objects.create(user=user, role=role, org_unit=branch, origin=RoleAssignment.Origin.MANUAL)

    c = APIClient()

    # Flujo real: login => JWT => JWTAuthWithOrgContext inyecta company/branch
    login = c.post(
        "/api/auth/login/",
        {"username": user.username, "password": "x"},
        format="json",
        HTTP_X_AUTH_TRANSPORT="header",
    )
    assert login.status_code == 200
    access = ""
    if isinstance(login.data, dict):
        candidate = login.data.get("access")
        if isinstance(candidate, str):
            access = candidate
    if access:
        c.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        c.defaults["HTTP_AUTHORIZATION"] = f"Bearer {access}"
    c.defaults["HTTP_X_AUTH_TRANSPORT"] = "header"

    c.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    c.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    return c


@pytest.mark.django_db
def test_billing_create_issue_void_audited():
    company, branch = _mk_scope()
    user = User.objects.create_user(username="u2", password="x")
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)

    c = _client_with_perms(
        user,
        company,
        branch,
        ["billing.doc.create", "billing.doc.read", "billing.doc.issue", "billing.doc.void"],
    )

    r = c.post(
        "/api/billing/docs/",
        {
            "doc_type": "INVOICE",
            "series": "A",
            "currency": "NIO",
            "customer_name": "Cliente 1",
            "is_fiscal": True,
            "idempotency_key": "b1",
            "lines": [
                {"description": "Servicio", "quantity": "1.0000", "unit_price": "100.000000", "tax_rate": "0.1500"},
            ],
        },
        format="json",
    )
    assert r.status_code == 201
    doc_id = r.data["id"]

    r = c.post(f"/api/billing/docs/{doc_id}/issue/", {"apply_inventory": False}, format="json")
    assert r.status_code == 200
    assert r.data["ok"] is True

    r = c.post(f"/api/billing/docs/{doc_id}/void/", {"reason": "Cliente canceló"}, format="json")
    assert r.status_code == 200
    assert r.data["ok"] is True

    assert AuditEvent.objects.filter(module="BILLING", event_type="BILLING_DOC_CREATED").count() >= 1
    assert AuditEvent.objects.filter(module="BILLING", event_type="BILLING_DOC_ISSUED").count() >= 1
    assert AuditEvent.objects.filter(module="BILLING", event_type="BILLING_DOC_VOIDED").count() >= 1


@pytest.mark.django_db
def test_billing_doc_cannot_void_draft():
    company, branch = _mk_scope()
    user = User.objects.create_user(username="u3", password="x")
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)

    c = _client_with_perms(
        user,
        company,
        branch,
        ["billing.doc.create", "billing.doc.void"],
    )

    r = c.post(
        "/api/billing/docs/",
        {
            "doc_type": "INVOICE",
            "series": "A",
            "currency": "NIO",
            "customer_name": "Cliente 2",
            "is_fiscal": False,
            "idempotency_key": "b2",
            "lines": [
                {"description": "Servicio", "quantity": "1.0000", "unit_price": "50.000000", "tax_rate": "0.1500"},
            ],
        },
        format="json",
    )
    assert r.status_code == 201
    doc_id = r.data["id"]

    r = c.post(f"/api/billing/docs/{doc_id}/void/", {"reason": "No emitido"}, format="json")
    assert r.status_code == 400
    assert "draft" in r.data["error"]["message"]


@pytest.mark.django_db
def test_billing_doc_issue_idempotent():
    company, branch = _mk_scope()
    user = User.objects.create_user(username="u4", password="x")
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)

    c = _client_with_perms(
        user,
        company,
        branch,
        ["billing.doc.create", "billing.doc.issue"],
    )

    r = c.post(
        "/api/billing/docs/",
        {
            "doc_type": "INVOICE",
            "series": "A",
            "currency": "NIO",
            "customer_name": "Cliente 3",
            "is_fiscal": False,
            "idempotency_key": "b3",
            "lines": [
                {"description": "Servicio", "quantity": "1.0000", "unit_price": "25.000000", "tax_rate": "0.1500"},
            ],
        },
        format="json",
    )
    assert r.status_code == 201
    doc_id = r.data["id"]

    r1 = c.post(f"/api/billing/docs/{doc_id}/issue/", {"apply_inventory": False}, format="json")
    assert r1.status_code == 200
    assert r1.data["ok"] is True

    r2 = c.post(f"/api/billing/docs/{doc_id}/issue/", {"apply_inventory": False}, format="json")
    assert r2.status_code == 200
    assert r2.data.get("already_issued") is True


@pytest.mark.django_db
def test_billing_docs_list_filters_pagination_and_scoping():
    company, branch = _mk_scope()
    branch_2 = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B2", parent=company)

    user = User.objects.create_user(username="u5", password="x")
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch_2, is_active=True)

    c = _client_with_perms(
        user,
        company,
        branch,
        ["billing.doc.create", "billing.doc.read", "billing.doc.issue", "billing.doc.void"],
    )

    created_1 = c.post(
        "/api/billing/docs/",
        {
            "doc_type": "INVOICE",
            "series": "A",
            "currency": "NIO",
            "customer_name": "Cliente Alpha",
            "customer_ref": "ALPHA-REF",
            "is_fiscal": False,
            "idempotency_key": "b-list-1",
            "lines": [
                {"description": "Servicio A", "quantity": "1.0000", "unit_price": "10.000000", "tax_rate": "0.1500"},
            ],
        },
        format="json",
    )
    assert created_1.status_code == 201
    draft_doc_id = int(created_1.data["id"])

    created_2 = c.post(
        "/api/billing/docs/",
        {
            "doc_type": "INVOICE",
            "series": "B",
            "currency": "NIO",
            "customer_name": "Cliente Numero",
            "customer_ref": "NUM-REF",
            "is_fiscal": False,
            "idempotency_key": "b-list-2",
            "lines": [
                {"description": "Servicio B", "quantity": "2.0000", "unit_price": "20.000000", "tax_rate": "0.1500"},
            ],
        },
        format="json",
    )
    assert created_2.status_code == 201
    issued_doc_id = int(created_2.data["id"])
    issued = c.post(f"/api/billing/docs/{issued_doc_id}/issue/", {"apply_inventory": False}, format="json")
    assert issued.status_code == 200

    created_3 = c.post(
        "/api/billing/docs/",
        {
            "doc_type": "CREDIT_NOTE",
            "series": "A",
            "currency": "NIO",
            "customer_name": "Cliente Void",
            "customer_ref": "VOID-REF",
            "is_fiscal": False,
            "idempotency_key": "b-list-3",
            "lines": [
                {"description": "Servicio C", "quantity": "1.0000", "unit_price": "30.000000", "tax_rate": "0.1500"},
            ],
        },
        format="json",
    )
    assert created_3.status_code == 201
    void_doc_id = int(created_3.data["id"])
    issued_void = c.post(f"/api/billing/docs/{void_doc_id}/issue/", {"apply_inventory": False}, format="json")
    assert issued_void.status_code == 200
    voided = c.post(f"/api/billing/docs/{void_doc_id}/void/", {"reason": "CANCEL"}, format="json")
    assert voided.status_code == 200

    # Documento de otra sucursal no debe aparecer al listar scope branch_1.
    BillingDocument.objects.create(
        company=company,
        branch=branch_2,
        doc_type="INVOICE",
        status="DRAFT",
        series="A",
        number=0,
        currency="NIO",
        customer_name="Sucursal B2",
        customer_ref="B2",
        subtotal="1.00",
        tax_total="0.00",
        total="1.00",
        is_fiscal=False,
        idempotency_key="b-other-branch",
    )

    # Empujar un documento fuera de rango de fecha.
    BillingDocument.objects.filter(id=draft_doc_id).update(created_at=timezone.now() - timedelta(days=7))

    listed = c.get("/api/billing/docs/?limit=2&offset=0&ordering=-created_at")
    assert listed.status_code == 200
    assert listed.data["count"] == 3
    assert listed.data["limit"] == 2
    assert listed.data["offset"] == 0
    assert len(listed.data["results"]) == 2

    status_filtered = c.get("/api/billing/docs/?status=ISSUED")
    assert status_filtered.status_code == 200
    assert status_filtered.data["count"] == 1
    assert status_filtered.data["results"][0]["status"] == "ISSUED"
    assert int(status_filtered.data["results"][0]["id"]) == issued_doc_id

    type_filtered = c.get("/api/billing/docs/?doc_type=CREDIT_NOTE")
    assert type_filtered.status_code == 200
    assert type_filtered.data["count"] == 1
    assert type_filtered.data["results"][0]["doc_type"] == "CREDIT_NOTE"

    text_filtered = c.get("/api/billing/docs/?q=ALPHA-REF")
    assert text_filtered.status_code == 200
    assert text_filtered.data["count"] == 1
    assert int(text_filtered.data["results"][0]["id"]) == draft_doc_id

    detail = c.get(f"/api/billing/docs/{issued_doc_id}/")
    assert detail.status_code == 200
    assigned_number = int(detail.data["number"])
    number_filtered = c.get(f"/api/billing/docs/?q={assigned_number}")
    assert number_filtered.status_code == 200
    result_ids = {int(row["id"]) for row in number_filtered.data["results"]}
    assert issued_doc_id in result_ids

    today = timezone.localdate().isoformat()
    date_filtered = c.get(f"/api/billing/docs/?date_from={today}")
    assert date_filtered.status_code == 200
    # excluye draft_doc_id movido 7 días atrás y documento de branch_2
    assert date_filtered.data["count"] == 2


@pytest.mark.django_db
def test_billing_docs_list_requires_read_permission_and_validates_filters():
    company, branch = _mk_scope()
    user = User.objects.create_user(username="u6", password="x")
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)

    c_no_read = _client_with_perms(user, company, branch, ["billing.doc.create"])
    denied = c_no_read.get("/api/billing/docs/")
    assert denied.status_code == 403

    c_with_read = _client_with_perms(user, company, branch, ["billing.doc.read"])

    c_with_read.defaults.pop("HTTP_X_BRANCH_ID", None)
    missing_branch = c_with_read.get("/api/billing/docs/")
    assert missing_branch.status_code == 400
    assert "X-Branch-Id requerido" in str(missing_branch.data)

    # Restaurar header y validar errores de contrato en filtros.
    c_with_read.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    invalid_status = c_with_read.get("/api/billing/docs/?status=INVALID")
    assert invalid_status.status_code == 400
    assert "status" in invalid_status.data.get("error", {}).get("details", {})

    invalid_date = c_with_read.get("/api/billing/docs/?date_from=2026-99-99")
    assert invalid_date.status_code == 400
    assert "date_from" in invalid_date.data.get("error", {}).get("details", {})

    invalid_order = c_with_read.get("/api/billing/docs/?ordering=-issued_at")
    assert invalid_order.status_code == 400
    assert "ordering" in invalid_order.data.get("error", {}).get("details", {})
