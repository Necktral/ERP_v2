from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.kernels.facturacion.models import (
    BillingDocument,
    BillingPayment,
    DocStatus,
    PaymentStatus,
    SalesOrder,
    SalesOrderStatus,
)
from apps.kernels.facturacion.services import BillingError
from apps.modulos.iam.models import OrgUnit
from apps.modulos.sync_engine import handlers_billing
from apps.modulos.sync_engine.errors import SyncRejectError


def _mk_scope() -> tuple[OrgUnit, OrgUnit]:
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B", parent=company)
    return company, branch


def _request(company: OrgUnit, branch: OrgUnit | None):
    return SimpleNamespace(
        company=company,
        branch=branch,
        META={"REMOTE_ADDR": "127.0.0.1", "HTTP_USER_AGENT": "pytest"},
        path="/api/sync/batch/",
        method="POST",
        request_id="pytest-sync-billing",
    )


def _ctx(*, request, company: OrgUnit, branch: OrgUnit | None, command_id: str | None = None) -> dict:
    return {
        "request": request,
        "company_id": company.id,
        "branch_id": branch.id if branch is not None else None,
        "command_id": command_id or str(uuid.uuid4()),
    }


def _line(*, description: str = "Servicio offline", price: str = "100.000000") -> dict:
    return {
        "description": description,
        "quantity": "1.0000",
        "unit_price": price,
        "tax_rate": "0.1500",
    }


@pytest.mark.django_db
def test_billing_sync_handlers_create_issue_pay_order_and_idempotency() -> None:
    company, branch = _mk_scope()
    req = _request(company, branch)

    draft_payload = {
        "doc_type": "INVOICE",
        "series": "OFF",
        "currency": "NIO",
        "customer_name": "Cliente offline",
        "customer_ref": "SYNC-CUST-1",
        "payment_method": "CASH",
        "idempotency_key": "offline-draft-001",
        "lines": [_line()],
    }
    first = handlers_billing.handle_billing_draft_create(
        _ctx(request=req, company=company, branch=branch),
        draft_payload,
    )
    duplicate = handlers_billing.handle_billing_draft_create(
        _ctx(request=req, company=company, branch=branch),
        draft_payload,
    )

    doc_id = int(first["refs"]["doc_id"])
    assert duplicate["refs"]["doc_id"] == doc_id
    assert BillingDocument.objects.filter(company=company, id=doc_id).count() == 1
    doc = BillingDocument.objects.get(id=doc_id)
    assert doc.status == DocStatus.DRAFT
    assert doc.source_module == "SYNC"
    assert doc.total == Decimal("115.00")

    issued = handlers_billing.handle_billing_doc_issue(
        _ctx(request=req, company=company, branch=branch),
        {"doc_id": doc_id, "apply_inventory": False, "idempotency_key": "issue-001"},
    )
    assert issued["refs"]["doc_id"] == doc_id
    assert int(issued["refs"]["number"]) == 1
    doc.refresh_from_db()
    assert doc.status == DocStatus.ISSUED

    paid = handlers_billing.handle_billing_payment_add(
        _ctx(request=req, company=company, branch=branch),
        {
            "doc_id": doc_id,
            "payment_method": "CASH",
            "amount": "115.00",
            "currency": "NIO",
            "reference": "cashbox-1",
            "notes": "offline full payment",
            "auto_confirm": True,
        },
    )
    assert paid["refs"]["doc_id"] == doc_id
    assert paid["refs"]["amount_paid"] == "115.00"
    assert paid["refs"]["payment_status"] == PaymentStatus.PAID
    payment = BillingPayment.objects.get(doc_id=doc_id)
    assert payment.status == BillingPayment.Status.CONFIRMED
    assert payment.reference == "cashbox-1"

    order = handlers_billing.handle_billing_order_create(
        _ctx(request=req, company=company, branch=branch),
        {
            "customer_name": "Cliente encargo",
            "customer_ref": "ORDER-REF",
            "currency": "NIO",
            "notes": "pedido offline",
            "lines": [_line(description="Producto por encargo", price="40.000000")],
        },
    )
    order_id = int(order["refs"]["order_id"])
    assert order["refs"]["status"] == SalesOrderStatus.DRAFT
    assert SalesOrder.objects.get(id=order_id).total == Decimal("46.00")


@pytest.mark.django_db
def test_billing_sync_handlers_reject_schema_and_scope_errors() -> None:
    company, branch = _mk_scope()
    req = _request(company, branch)

    with pytest.raises(SyncRejectError) as exc:
        handlers_billing.handle_billing_draft_create(
            _ctx(request=req, company=company, branch=None),
            {"lines": [_line()]},
        )
    assert exc.value.reason_code == "BILLING_INVALID_SCOPE"
    assert exc.value.details == {"branch_id": "required"}

    with pytest.raises(SyncRejectError) as exc:
        handlers_billing.handle_billing_draft_create(
            _ctx(request=req, company=company, branch=branch),
            {"lines": []},
        )
    assert exc.value.reason_code == "BILLING_SCHEMA_INVALID"
    assert exc.value.details == {"lines": "required"}

    with pytest.raises(SyncRejectError) as exc:
        handlers_billing.handle_billing_doc_issue(
            _ctx(request=req, company=company, branch=branch),
            {"doc_id": "not-an-int"},
        )
    assert exc.value.reason_code == "BILLING_SCHEMA_INVALID"
    assert exc.value.details == {"doc_id": "invalid int"}

    with pytest.raises(SyncRejectError) as exc:
        handlers_billing.handle_billing_payment_add(
            _ctx(request=req, company=company, branch=branch),
            {"doc_id": 1, "amount": "1.00"},
        )
    assert exc.value.reason_code == "BILLING_SCHEMA_INVALID"
    assert exc.value.details == {"payment_method": "required"}

    with pytest.raises(SyncRejectError) as exc:
        handlers_billing.handle_billing_payment_add(
            _ctx(request=req, company=company, branch=branch),
            {"doc_id": 1, "payment_method": "CASH", "amount": "bad"},
        )
    assert exc.value.reason_code == "BILLING_SCHEMA_INVALID"
    assert exc.value.details == {"amount": "invalid"}

    with pytest.raises(SyncRejectError) as exc:
        handlers_billing.handle_billing_order_create(
            _ctx(request=req, company=company, branch=branch),
            {"lines": []},
        )
    assert exc.value.reason_code == "BILLING_SCHEMA_INVALID"
    assert exc.value.details == {"lines": "required"}


@pytest.mark.django_db
def test_billing_sync_error_mapping_preserves_contract_reason_codes() -> None:
    not_found = handlers_billing._map_billing_error(BillingError("documento no encontrado"))
    inventory = handlers_billing._map_billing_error(BillingError("stock insuficiente en bodega"))
    generic = handlers_billing._map_billing_error(BillingError("invalid payment_method"))

    assert not_found.reason_code == "BILLING_NOT_FOUND"
    assert inventory.reason_code == "BILLING_INVENTORY_ERROR"
    assert generic.reason_code == "BILLING_SCHEMA_INVALID"
