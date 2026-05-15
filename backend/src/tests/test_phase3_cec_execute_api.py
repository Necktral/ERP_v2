from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.kernels.facturacion.models import BillingDocument, DocStatus, DocType
from apps.kernels.payments.models import CashMovement, CashSession, PaymentIntent
from apps.modulos.common.tender import TenderPaymentMethod
from apps.modulos.estacion_servicios.models import (
    FuelDispense,
    FuelPaymentMethod,
    FuelProduct,
    FuelSale,
    FuelSaleStatus,
    FuelSaleType,
    FuelShift,
    FuelShiftStatus,
)
from apps.modulos.cec.models import CECException
from apps.modulos.iam.models import OrgUnit
from apps.modulos.integration.models import OutboxEvent
from apps.modulos.integration.services import publish_outbox_event
from tests.helpers.operational_auth import create_operational_api_actor as _client_with_perms


def _mk_org():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B", parent=company)
    return company, branch


def _create_fuel_billing_doc(*, company, branch, user, amount: Decimal, payment_method: str, issued_at):
    shift = FuelShift.objects.filter(company=company, branch=branch, status=FuelShiftStatus.OPEN).first()
    if shift is None:
        shift = FuelShift.objects.create(
            company=company,
            branch=branch,
            status=FuelShiftStatus.OPEN,
            opened_at=issued_at - timedelta(hours=2),
            opened_by=user,
        )
    dispense = FuelDispense.objects.create(
        company=company,
        branch=branch,
        shift=shift,
        occurred_at=issued_at - timedelta(minutes=30),
        recorded_by=user,
        product=FuelProduct.DIESEL,
        liters=Decimal("1.0000"),
        volume_entered=Decimal("1.0000"),
        unit_price=amount,
        unit_price_entered=amount,
        amount=amount,
        amount_canonical=amount,
    )
    sale = FuelSale.objects.create(
        company=company,
        branch=branch,
        shift=shift,
        dispense=dispense,
        sale_type=FuelSaleType.PUBLIC,
        payment_method=payment_method,
        total_amount=amount,
        status=FuelSaleStatus.ACTIVE,
        created_at=issued_at,
        created_by=user,
    )
    doc = BillingDocument.objects.create(
        company=company,
        branch=branch,
        doc_type=DocType.INVOICE,
        status=DocStatus.ISSUED,
        series="FUEL",
        number=int(sale.id),
        currency="NIO",
        subtotal=amount,
        tax_total=Decimal("0.00"),
        total=amount,
        source_module="FUEL",
        source_type="SALE",
        source_id=str(sale.id),
        issued_at=issued_at,
        created_by=user,
        created_at=issued_at,
    )
    sale.billing_doc = doc
    sale.save(update_fields=["billing_doc"])
    return sale, doc


def _create_unknown_billing_doc(*, company, branch, user, amount: Decimal, issued_at):
    return BillingDocument.objects.create(
        company=company,
        branch=branch,
        doc_type=DocType.INVOICE,
        status=DocStatus.ISSUED,
        series="MANUAL",
        number=9000,
        currency="NIO",
        subtotal=amount,
        tax_total=Decimal("0.00"),
        total=amount,
        issued_at=issued_at,
        created_by=user,
        created_at=issued_at,
    )


def _create_cash_income(*, company, branch, user, amount: Decimal, created_at):
    session = CashSession.objects.create(
        company=company,
        branch=branch,
        opened_by=user,
        status=CashSession.Status.OPEN,
        opened_at=created_at - timedelta(hours=1),
        opening_amount=Decimal("0.00"),
        expected_amount=amount,
        counted_amount=Decimal("0.00"),
        difference_amount=Decimal("0.00"),
    )
    return CashMovement.objects.create(
        session=session,
        movement_type=CashMovement.MovementType.INCOME,
        amount=amount,
        reference="cec-tender-test",
        reason="TEST_CASH",
        created_by=user,
        created_at=created_at,
    )


def _execute_daily_close(*, client, now, strict: bool = True):
    run_resp = client.post("/api/cec/close-runs/", {"run_type": "DAILY"}, format="json")
    assert run_resp.status_code == 201
    run_id = run_resp.data["run_id"]
    execute_resp = client.post(
        f"/api/cec/close-runs/{run_id}/execute/",
        {
            "window_start": (now - timedelta(days=1)).isoformat(),
            "window_end": (now + timedelta(days=1)).isoformat(),
            "strict": strict,
        },
        format="json",
    )
    assert execute_resp.status_code == 200
    return run_id, execute_resp


def _billing_cash_metric(execute_resp):
    for gate in execute_resp.data["gates"]:
        if gate["name"] == "billing_vs_cash_reconciliation":
            return gate["metric"]
    raise AssertionError("billing_vs_cash_reconciliation gate not found")


@pytest.mark.django_db
def test_cec_execute_success_and_summary_endpoint():
    company, branch = _mk_org()
    client, _ = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["cec.close_run.read", "cec.close_run.create", "cec.close_run.update"],
    )

    run_resp = client.post("/api/cec/close-runs/", {"run_type": "DAILY"}, format="json")
    assert run_resp.status_code == 201
    run_id = run_resp.data["run_id"]

    now = timezone.now()
    execute_resp = client.post(
        f"/api/cec/close-runs/{run_id}/execute/",
        {
            "window_start": (now - timedelta(days=1)).isoformat(),
            "window_end": (now + timedelta(days=1)).isoformat(),
            "strict": True,
        },
        format="json",
    )
    assert execute_resp.status_code == 200
    assert execute_resp.data["status"] == "PACKAGED"
    assert execute_resp.data["blocking_exceptions_count"] == 0
    assert len(execute_resp.data["output_manifest_hash"]) == 64

    summary_resp = client.get(f"/api/cec/close-runs/{run_id}/summary/")
    assert summary_resp.status_code == 200
    assert summary_resp.data["status"] == "PACKAGED"
    assert summary_resp.data["consistency_score"] == 100
    assert isinstance(summary_resp.data["summary"], dict)
    assert isinstance(summary_resp.data["exceptions"], list)


@pytest.mark.django_db
def test_cec_billing_cash_reconciliation_counts_only_cash_fuel_sales():
    company, branch = _mk_org()
    client, user = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["cec.close_run.read", "cec.close_run.create", "cec.close_run.update"],
    )
    now = timezone.now()
    _create_fuel_billing_doc(
        company=company,
        branch=branch,
        user=user,
        amount=Decimal("100.00"),
        payment_method=FuelPaymentMethod.CASH,
        issued_at=now - timedelta(minutes=20),
    )
    _create_cash_income(company=company, branch=branch, user=user, amount=Decimal("100.00"), created_at=now - timedelta(minutes=10))

    _, execute_resp = _execute_daily_close(client=client, now=now)

    assert execute_resp.data["status"] == "PACKAGED"
    metric = _billing_cash_metric(execute_resp)
    assert metric["billing_total"] == "100.00"
    assert metric["cash_expected_billing_total"] == "100.00"
    assert metric["cash_total"] == "100.00"
    assert metric["difference"] == "0.00"
    assert metric["cash_expected_billing_count"] == 1
    assert metric["non_cash_billing_count"] == 0
    assert metric["unknown_tender_billing_count"] == 0


@pytest.mark.django_db
def test_cec_prefers_billing_payment_method_snapshot_before_source_lookup():
    company, branch = _mk_org()
    client, user = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["cec.close_run.read", "cec.close_run.create", "cec.close_run.update"],
    )
    now = timezone.now()
    _sale, doc = _create_fuel_billing_doc(
        company=company,
        branch=branch,
        user=user,
        amount=Decimal("90.00"),
        payment_method=FuelPaymentMethod.TRANSFER,
        issued_at=now - timedelta(minutes=20),
    )
    doc.payment_method = TenderPaymentMethod.CASH
    doc.save(update_fields=["payment_method"])
    _create_cash_income(company=company, branch=branch, user=user, amount=Decimal("90.00"), created_at=now - timedelta(minutes=10))

    _, execute_resp = _execute_daily_close(client=client, now=now)

    assert execute_resp.data["status"] == "PACKAGED"
    metric = _billing_cash_metric(execute_resp)
    assert metric["cash_expected_billing_total"] == "90.00"
    assert metric["non_cash_billing_total"] == "0.00"
    assert metric["difference"] == "0.00"
    assert not CECException.objects.filter(code="BILLING_CASH_MISMATCH").exists()


@pytest.mark.django_db
def test_cec_transfer_and_credit_fuel_sales_do_not_create_cash_mismatch():
    company, branch = _mk_org()
    client, user = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["cec.close_run.read", "cec.close_run.create", "cec.close_run.update"],
    )
    now = timezone.now()
    _create_fuel_billing_doc(
        company=company,
        branch=branch,
        user=user,
        amount=Decimal("120.00"),
        payment_method=FuelPaymentMethod.TRANSFER,
        issued_at=now - timedelta(minutes=20),
    )
    _create_fuel_billing_doc(
        company=company,
        branch=branch,
        user=user,
        amount=Decimal("80.00"),
        payment_method=FuelPaymentMethod.CREDIT,
        issued_at=now - timedelta(minutes=10),
    )

    _, execute_resp = _execute_daily_close(client=client, now=now)

    assert execute_resp.data["status"] == "PACKAGED"
    metric = _billing_cash_metric(execute_resp)
    assert metric["billing_total"] == "200.00"
    assert metric["cash_expected_billing_total"] == "0.00"
    assert metric["non_cash_billing_total"] == "200.00"
    assert metric["transfer_billing_total"] == "120.00"
    assert metric["credit_billing_total"] == "80.00"
    assert metric["card_billing_total"] == "0.00"
    assert metric["cash_total"] == "0.00"
    assert metric["difference"] == "0.00"
    assert metric["non_cash_billing_count"] == 2
    assert not CECException.objects.filter(code="BILLING_CASH_MISMATCH").exists()


@pytest.mark.django_db
def test_cec_card_billing_snapshot_is_non_cash_without_source_lookup():
    company, branch = _mk_org()
    client, user = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["cec.close_run.read", "cec.close_run.create", "cec.close_run.update"],
    )
    now = timezone.now()
    BillingDocument.objects.create(
        company=company,
        branch=branch,
        doc_type=DocType.INVOICE,
        status=DocStatus.ISSUED,
        series="CARD",
        number=9100,
        currency="NIO",
        subtotal=Decimal("55.00"),
        tax_total=Decimal("0.00"),
        total=Decimal("55.00"),
        payment_method=TenderPaymentMethod.CARD,
        issued_at=now - timedelta(minutes=20),
        created_by=user,
        created_at=now - timedelta(minutes=20),
    )

    _, execute_resp = _execute_daily_close(client=client, now=now)

    assert execute_resp.data["status"] == "PACKAGED"
    metric = _billing_cash_metric(execute_resp)
    assert metric["billing_total"] == "55.00"
    assert metric["cash_expected_billing_total"] == "0.00"
    assert metric["non_cash_billing_total"] == "55.00"
    assert metric["card_billing_total"] == "55.00"
    assert metric["unknown_tender_billing_total"] == "0.00"
    assert metric["difference"] == "0.00"
    assert not CECException.objects.filter(code="BILLING_CASH_MISMATCH").exists()


@pytest.mark.django_db
def test_cec_cash_fuel_sale_mismatch_still_blocks_strict_close():
    company, branch = _mk_org()
    client, user = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["cec.close_run.read", "cec.close_run.create", "cec.close_run.update"],
    )
    now = timezone.now()
    _create_fuel_billing_doc(
        company=company,
        branch=branch,
        user=user,
        amount=Decimal("100.00"),
        payment_method=FuelPaymentMethod.CASH,
        issued_at=now - timedelta(minutes=20),
    )
    _create_cash_income(company=company, branch=branch, user=user, amount=Decimal("60.00"), created_at=now - timedelta(minutes=10))

    _, execute_resp = _execute_daily_close(client=client, now=now, strict=True)

    assert execute_resp.data["status"] == "REOPENED_EXCEPTION"
    metric = _billing_cash_metric(execute_resp)
    assert metric["billing_total"] == "100.00"
    assert metric["cash_expected_billing_total"] == "100.00"
    assert metric["cash_total"] == "60.00"
    assert metric["difference"] == "40.00"
    assert CECException.objects.filter(code="BILLING_CASH_MISMATCH", is_blocking=True).exists()


@pytest.mark.django_db
def test_cec_unknown_tender_billing_is_reported_but_not_counted_as_cash_expected():
    company, branch = _mk_org()
    client, user = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["cec.close_run.read", "cec.close_run.create", "cec.close_run.update"],
    )
    now = timezone.now()
    _create_unknown_billing_doc(
        company=company,
        branch=branch,
        user=user,
        amount=Decimal("70.00"),
        issued_at=now - timedelta(minutes=20),
    )

    _, execute_resp = _execute_daily_close(client=client, now=now)

    assert execute_resp.data["status"] == "PACKAGED"
    metric = _billing_cash_metric(execute_resp)
    assert metric["billing_total"] == "70.00"
    assert metric["cash_expected_billing_total"] == "0.00"
    assert metric["unknown_tender_billing_total"] == "70.00"
    assert metric["unknown_tender_billing_count"] == 1
    assert metric["cash_total"] == "0.00"
    assert metric["difference"] == "0.00"
    assert not CECException.objects.filter(code="BILLING_CASH_MISMATCH").exists()


@pytest.mark.django_db
def test_cec_unknown_tender_cash_is_tolerated_and_reported_without_cash_expected():
    company, branch = _mk_org()
    client, user = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["cec.close_run.read", "cec.close_run.create", "cec.close_run.update"],
    )
    now = timezone.now()
    _create_unknown_billing_doc(
        company=company,
        branch=branch,
        user=user,
        amount=Decimal("70.00"),
        issued_at=now - timedelta(minutes=20),
    )
    _create_cash_income(company=company, branch=branch, user=user, amount=Decimal("70.00"), created_at=now - timedelta(minutes=10))

    _, execute_resp = _execute_daily_close(client=client, now=now)

    assert execute_resp.data["status"] == "PACKAGED"
    metric = _billing_cash_metric(execute_resp)
    assert metric["billing_total"] == "70.00"
    assert metric["cash_expected_billing_total"] == "0.00"
    assert metric["unknown_tender_billing_total"] == "70.00"
    assert metric["cash_total"] == "70.00"
    assert metric["cash_reconciled_total"] == "0.00"
    assert metric["cash_surplus_tolerated_by_unknown_tender_total"] == "70.00"
    assert metric["difference"] == "0.00"
    assert not CECException.objects.filter(code="BILLING_CASH_MISMATCH").exists()


@pytest.mark.django_db
def test_cec_payment_captured_event_does_not_affect_cash_reconciliation():
    company, branch = _mk_org()
    client, user = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["cec.close_run.read", "cec.close_run.create", "cec.close_run.update"],
    )
    now = timezone.now()
    intent = PaymentIntent.objects.create(
        company=company,
        branch=branch,
        amount=Decimal("99.00"),
        status=PaymentIntent.Status.CAPTURED,
        provider="POS",
        provider_txn_id="pos:test",
        captured_at=now - timedelta(minutes=10),
    )
    publish_outbox_event(
        source_module="PAYMENTS",
        event_type="PaymentCaptured",
        payload={
            "payment_id": str(intent.payment_id),
            "amount": str(intent.amount),
            "currency": intent.currency,
            "status": intent.status,
            "provider_txn_id": intent.provider_txn_id,
        },
        actor_user=user,
        company=company,
        branch=branch,
    )

    _, execute_resp = _execute_daily_close(client=client, now=now)

    assert execute_resp.data["status"] == "PACKAGED"
    metric = _billing_cash_metric(execute_resp)
    assert metric["billing_total"] == "0.00"
    assert metric["cash_expected_billing_total"] == "0.00"
    assert metric["cash_total"] == "0.00"
    assert metric["difference"] == "0.00"


@pytest.mark.django_db
def test_cec_execute_blocked_when_cash_difference_exists():
    company, branch = _mk_org()
    client, user = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["cec.close_run.read", "cec.close_run.create", "cec.close_run.update", "cec.evidence.create"],
    )

    run_resp = client.post("/api/cec/close-runs/", {"run_type": "DAILY"}, format="json")
    assert run_resp.status_code == 201
    run_id = run_resp.data["run_id"]

    now = timezone.now()
    CashSession.objects.create(
        company=company,
        branch=branch,
        opened_by=user,
        closed_by=user,
        status=CashSession.Status.CLOSED,
        opened_at=now - timedelta(hours=4),
        closed_at=now - timedelta(hours=1),
        opening_amount=Decimal("100.00"),
        expected_amount=Decimal("180.00"),
        counted_amount=Decimal("170.00"),
        difference_amount=Decimal("-10.00"),
    )

    execute_resp = client.post(
        f"/api/cec/close-runs/{run_id}/execute/",
        {
            "window_start": (now - timedelta(days=1)).isoformat(),
            "window_end": (now + timedelta(days=1)).isoformat(),
            "strict": True,
        },
        format="json",
    )
    assert execute_resp.status_code == 200
    assert execute_resp.data["status"] == "REOPENED_EXCEPTION"
    assert execute_resp.data["blocking_exceptions_count"] >= 1

    outbox_types = set(
        OutboxEvent.objects.filter(source_module="CEC").values_list("event_type", flat=True)
    )
    assert "CloseRunExecuted" in outbox_types
    assert "CloseRunBlocked" in outbox_types


@pytest.mark.django_db
def test_cec_execute_with_strict_false_still_blocks_cash_difference():
    company, branch = _mk_org()
    client, user = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["cec.close_run.read", "cec.close_run.create", "cec.close_run.update"],
    )

    run_resp = client.post("/api/cec/close-runs/", {"run_type": "DAILY"}, format="json")
    assert run_resp.status_code == 201
    run_id = run_resp.data["run_id"]

    now = timezone.now()
    CashSession.objects.create(
        company=company,
        branch=branch,
        opened_by=user,
        closed_by=user,
        status=CashSession.Status.CLOSED,
        opened_at=now - timedelta(hours=4),
        closed_at=now - timedelta(hours=1),
        opening_amount=Decimal("100.00"),
        expected_amount=Decimal("180.00"),
        counted_amount=Decimal("170.00"),
        difference_amount=Decimal("-10.00"),
    )

    execute_resp = client.post(
        f"/api/cec/close-runs/{run_id}/execute/",
        {
            "window_start": (now - timedelta(days=1)).isoformat(),
            "window_end": (now + timedelta(days=1)).isoformat(),
            "strict": False,
        },
        format="json",
    )
    assert execute_resp.status_code == 200
    assert execute_resp.data["status"] == "REOPENED_EXCEPTION"
    assert execute_resp.data["blocking_exceptions_count"] >= 1


@pytest.mark.django_db
def test_cec_advance_rejects_invalid_transition_with_409():
    company, branch = _mk_org()
    client, _ = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["cec.close_run.create", "cec.close_run.update"],
    )
    run_resp = client.post("/api/cec/close-runs/", {"run_type": "DAILY"}, format="json")
    assert run_resp.status_code == 201
    run_id = run_resp.data["run_id"]

    invalid = client.post(
        f"/api/cec/close-runs/{run_id}/advance/",
        {"status": "PACKAGED"},
        format="json",
    )
    assert invalid.status_code == 409
